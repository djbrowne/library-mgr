from flask import Blueprint, render_template, request
from app.models import Loan, BookCopy, Title, User, AuditLog
from app.services.metadata_service import clean_isbn

bp = Blueprint('reports', __name__)

@bp.route('/active-loans')
def active_loans():
    loans = Loan.query.filter_by(status='active').order_by(Loan.due_date.asc()).all()
    return render_template('reports/active_loans.html', loans=loans)

@bp.route('/condition')
def condition_report():
    selected_condition = request.args.get('condition', '').strip()
    query = BookCopy.query.filter(BookCopy.status != 'removed')
    if selected_condition in ['new', 'good', 'damaged']:
        query = query.filter_by(condition=selected_condition)

    copies = query.order_by(BookCopy.condition.asc(), BookCopy.copy_id.asc()).all()

    counts = {
        'new': BookCopy.query.filter_by(condition='new').count(),
        'good': BookCopy.query.filter_by(condition='good').count(),
        'damaged': BookCopy.query.filter_by(condition='damaged').count()
    }

    return render_template('reports/condition.html', copies=copies, counts=counts, selected_condition=selected_condition)

@bp.route('/book-history')
def book_history():
    identifier = request.args.get('identifier', '').strip()
    history = []
    audit_events = []
    copy = None
    title = None

    if identifier:
        # Check if copy ID
        copy = BookCopy.query.filter_by(copy_id=identifier).first()
        if copy:
            history = Loan.query.filter_by(copy_id=copy.copy_id).order_by(Loan.checkout_date.desc()).all()
            audit_events = AuditLog.query.filter_by(copy_id=copy.copy_id).order_by(AuditLog.timestamp.desc()).all()
            title = copy.title
        else:
            clean = clean_isbn(identifier)
            title = Title.query.filter_by(isbn=clean).first()
            if title:
                copy_ids = [c.copy_id for c in title.copies]
                history = Loan.query.filter(Loan.copy_id.in_(copy_ids)).order_by(Loan.checkout_date.desc()).all()
                audit_events = AuditLog.query.filter(
                    (AuditLog.isbn == clean) | (AuditLog.copy_id.in_(copy_ids))
                ).order_by(AuditLog.timestamp.desc()).all()

    return render_template(
        'reports/book_history.html',
        identifier=identifier,
        copy=copy,
        title=title,
        history=history,
        audit_events=audit_events
    )

@bp.route('/user-history')
def user_history():
    user_id = request.args.get('user_id', '').strip()
    user = None
    loans = []
    audit_events = []

    if user_id:
        user = User.query.filter_by(user_id=user_id).first()
        if user:
            loans = Loan.query.filter_by(user_id=user.user_id).order_by(Loan.checkout_date.desc()).all()
            audit_events = AuditLog.query.filter_by(user_id=user.user_id).order_by(AuditLog.timestamp.desc()).all()

    return render_template('reports/user_history.html', user_id=user_id, user=user, loans=loans, audit_events=audit_events)

@bp.route('/audit-log')
def audit_log():
    action_filter = request.args.get('action', '').strip()
    query = AuditLog.query
    if action_filter:
        query = query.filter_by(action=action_filter)
    events = query.order_by(AuditLog.timestamp.desc()).limit(100).all()
    return render_template('reports/audit_log.html', events=events, action_filter=action_filter)
