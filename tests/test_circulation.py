from datetime import timedelta
from app.models import BookCopy, Loan, Hold, AuditLog, utc_now
from app.services.circulation_service import checkout_book, checkin_book, place_hold

def test_checkout_and_checkin_flow(app):
    with app.app_context():
        # Check out copy 1
        success, msg, loan, copy = checkout_book(user_id="1001", identifier="9780132350884-1", loan_days=60)
        assert success is True
        assert copy.status == "borrowed"
        assert loan.status == "active"
        assert loan.user_id == "1001"
        assert loan.copy_id == "9780132350884-1"
        # Due date is approximately 60 days in future
        diff = loan.due_date - loan.checkout_date
        assert diff.days == 60

        # Verify audit log was written
        audit = AuditLog.query.filter_by(action="CHECKOUT", copy_id="9780132350884-1").first()
        assert audit is not None
        assert audit.user_id == "1001"

        # Return book via checkin
        in_success, in_msg, in_loan, in_copy = checkin_book(identifier="9780132350884-1", condition_override="good")
        assert in_success is True
        assert in_copy.status == "available"
        assert in_copy.condition == "good"
        assert in_loan.status == "returned"
        assert in_loan.returned_date is not None

        # Verify return audit log
        return_audit = AuditLog.query.filter_by(action="CHECKIN", copy_id="9780132350884-1").first()
        assert return_audit is not None

def test_auto_resolve_single_borrowed_copy(app):
    with app.app_context():
        # Check out copy 2 specifically
        checkout_book(user_id="1001", identifier="9780132350884-2")
        
        # Now check in by raw ISBN only (since only copy 2 is borrowed, it should auto-resolve)
        success, msg, loan, copy = checkin_book(identifier="9780132350884")
        assert success is True
        assert copy.copy_id == "9780132350884-2"
        assert copy.status == "available"

def test_hold_and_status_transitions(app):
    with app.app_context():
        # Both copies checked out
        checkout_book("1001", "9780132350884-1")
        checkout_book("1001", "9780132350884-2")

        # Admin user 0001 places hold on ISBN
        h_success, h_msg = place_hold(user_id="0001", isbn="9780132350884")
        assert h_success is True

        # Copies should now show borrowed_and_on_hold
        c1 = BookCopy.query.filter_by(copy_id="9780132350884-1").first()
        assert c1.status == "borrowed_and_on_hold"

        # Check in copy 1 -> status should transition to 'on_hold' because user 0001 is waiting!
        in_success, in_msg, in_loan, in_copy = checkin_book("9780132350884-1")
        assert in_success is True
        assert in_copy.status == "on_hold"
        assert "User 0001" in in_msg

def test_invalid_user_rejection(app):
    with app.app_context():
        # Invalid 4-digit ID not in database
        success, msg, loan, copy = checkout_book(user_id="9999", identifier="9780132350884-1")
        assert success is False
        assert "does not exist" in msg
