from datetime import timedelta
from app.db import db
from app.models import User, Title, BookCopy, Loan, Hold, utc_now
from app.services.audit_service import record_audit
from app.services.metadata_service import clean_isbn

def resolve_copy_identifier(identifier: str):
    """
    Parses an identifier which could be a specific Copy ID (e.g. '9780132350884-1')
    or a raw ISBN (e.g. '9780132350884').
    Returns (clean_isbn, copy_number_or_none, exact_copy_or_none).
    """
    if not identifier:
        return None, None, None
    raw = identifier.strip()
    if '-' in raw:
        parts = raw.rsplit('-', 1)
        base_clean = clean_isbn(parts[0])
        try:
            num = int(parts[1])
            copy = BookCopy.query.filter_by(copy_id=f"{base_clean}-{num}").first()
            return base_clean, num, copy
        except ValueError:
            pass

    clean = clean_isbn(raw)
    exact = BookCopy.query.filter_by(copy_id=clean).first()
    return clean, None, exact

def checkout_book(user_id: str, identifier: str, loan_days: int = 60):
    """
    Checks out a book copy to a 4-digit user ID.
    Returns (success_boolean, message, loan_object_or_none, copy_object_or_none).
    """
    user_id = str(user_id).strip()
    user = User.query.filter_by(user_id=user_id, is_active=True).first()
    if not user:
        return False, f"User ID '{user_id}' does not exist or is deactivated.", None, None

    clean, num, copy = resolve_copy_identifier(identifier)
    if not clean:
        return False, "Invalid ISBN or copy identifier provided.", None, None

    # If specific copy not resolved by exact ID, find available copy of ISBN
    if not copy:
        title = Title.query.filter_by(isbn=clean).first()
        if not title:
            return False, f"No catalog entry found for ISBN {clean}.", None, None
        
        # Check if user has a hold ready or waiting on this ISBN
        user_hold = Hold.query.filter_by(isbn=clean, user_id=user_id, status='waiting').first()

        # Find available copies
        available_copies = title.copies.filter_by(status='available').all()
        if not available_copies:
            # Check if there is an 'on_hold' copy
            on_hold_copy = title.copies.filter_by(status='on_hold').first()
            if on_hold_copy and user_hold:
                copy = on_hold_copy
            else:
                return False, f"All copies of '{title.title}' are currently checked out or unavailable.", None, None
        else:
            copy = available_copies[0]

    # Validate copy status
    if copy.status in ['removed', 'lost']:
        return False, f"Book copy {copy.copy_id} is marked as {copy.status} and cannot be checked out.", None, None

    if copy.status == 'borrowed' or copy.status == 'borrowed_and_on_hold':
        return False, f"Book copy {copy.copy_id} is already checked out.", None, None

    # Check if on hold for someone else
    waiting_holds = Hold.query.filter_by(isbn=copy.isbn, status='waiting').order_by(Hold.placed_at.asc()).all()
    if waiting_holds:
        first_hold = waiting_holds[0]
        if first_hold.user_id != user.user_id and copy.status == 'on_hold':
            return False, f"Book copy {copy.copy_id} is currently held for user {first_hold.user_id}.", None, None
        elif first_hold.user_id == user.user_id:
            first_hold.status = 'fulfilled'

    # Check if there are other waiting holds after this checkout
    remaining_holds = [h for h in waiting_holds if h.user_id != user.user_id and h.status == 'waiting']
    new_status = 'borrowed_and_on_hold' if remaining_holds else 'borrowed'

    checkout_time = utc_now()
    due_time = checkout_time + timedelta(days=loan_days)

    loan = Loan(
        copy_id=copy.copy_id,
        user_id=user.user_id,
        checkout_date=checkout_time,
        due_date=due_time,
        status='active'
    )
    db.session.add(loan)

    prev_status = copy.status
    copy.status = new_status
    db.session.flush()

    record_audit(
        action='CHECKOUT',
        copy_id=copy.copy_id,
        isbn=copy.isbn,
        user_id=user.user_id,
        previous_state=f"status={prev_status}",
        new_state=f"status={copy.status}, loan_id={loan.loan_id}",
        notes=f"Checked out to {user.name} ({user.user_id}) until {due_time.strftime('%Y-%m-%d')}"
    )

    db.session.commit()
    msg = f"Successfully checked out '{copy.title.title}' ({copy.copy_id}) to {user.name}."
    return True, msg, loan, copy

def checkin_book(identifier: str, condition_override: str = None, return_notes: str = None):
    """
    Checks in a book copy using either Copy ID or ISBN.
    Returns (success_boolean, message, loan_object_or_none, copy_object_or_none).
    """
    clean, num, copy = resolve_copy_identifier(identifier)
    if not clean:
        return False, "Invalid ISBN or copy identifier.", None, None

    # If copy not specified, look for currently borrowed copies of this ISBN
    if not copy:
        borrowed_copies = BookCopy.query.filter(
            BookCopy.isbn == clean,
            BookCopy.status.in_(['borrowed', 'borrowed_and_on_hold'])
        ).all()

        if not borrowed_copies:
            # Check if copy exists but is already available
            existing = BookCopy.query.filter_by(isbn=clean).first()
            if existing:
                return False, f"All copies of ISBN {clean} appear to be already checked in (status: {existing.status}).", None, None
            return False, f"No copies found for ISBN {clean}.", None, None

        if len(borrowed_copies) == 1:
            copy = borrowed_copies[0]
        else:
            return False, f"Multiple copies of this ISBN are currently checked out ({', '.join(c.copy_id for c in borrowed_copies)}). Please enter the specific copy ID (e.g. {borrowed_copies[0].copy_id}).", None, None

    active_loan = copy.active_loan
    prev_status = copy.status

    if not active_loan:
        # Book is in library or has no active loan record
        return False, f"Copy {copy.copy_id} does not have an active checkout record. Current status is '{copy.status}'.", None, copy

    # Update active loan
    return_time = utc_now()
    active_loan.status = 'returned'
    active_loan.returned_date = return_time
    if condition_override:
        active_loan.return_condition = condition_override
        copy.condition = condition_override

    # Check for waiting holds on this title
    waiting_hold = Hold.query.filter_by(isbn=copy.isbn, status='waiting').order_by(Hold.placed_at.asc()).first()
    if waiting_hold:
        copy.status = 'on_hold'
        shelving_msg = f"NOTE: Book is on hold for User {waiting_hold.user_id}! Please place it in the Hold / Reservation pickup area."
    else:
        copy.status = 'available'
        shelving_msg = "Please place it in the library room for re-shelving."

    db.session.flush()

    record_audit(
        action='CHECKIN',
        copy_id=copy.copy_id,
        isbn=copy.isbn,
        user_id=active_loan.user_id,
        previous_state=f"status={prev_status}, loan_id={active_loan.loan_id}",
        new_state=f"status={copy.status}, condition={copy.condition}",
        notes=f"Returned by user {active_loan.user_id}. {return_notes or ''}".strip()
    )

    db.session.commit()
    msg = f"Check-in successful for '{copy.title.title}' ({copy.copy_id}). {shelving_msg}"
    return True, msg, active_loan, copy

def place_hold(user_id: str, isbn: str):
    """
    Places a reservation hold for a user on a book title.
    Returns (success_boolean, message).
    """
    user_id = str(user_id).strip()
    user = User.query.filter_by(user_id=user_id, is_active=True).first()
    if not user:
        return False, f"User {user_id} not found or inactive."

    clean = clean_isbn(isbn)
    title = Title.query.filter_by(isbn=clean).first()
    if not title:
        return False, f"Title with ISBN {clean} not found."

    # Check if user already has an active hold
    existing_hold = Hold.query.filter_by(isbn=clean, user_id=user_id, status='waiting').first()
    if existing_hold:
        return False, f"User {user_id} already has a waiting hold on '{title.title}'."

    hold = Hold(
        isbn=clean,
        user_id=user_id,
        placed_at=utc_now(),
        status='waiting'
    )
    db.session.add(hold)

    # Update borrowed copies of this title to borrowed_and_on_hold
    for copy in title.copies.filter_by(status='borrowed'):
        copy.status = 'borrowed_and_on_hold'

    record_audit(
        action='HOLD_PLACED',
        isbn=clean,
        user_id=user_id,
        notes=f"Hold placed by {user.name} on '{title.title}'"
    )

    db.session.commit()
    return True, f"Hold placed successfully for {user.name} on '{title.title}'."
