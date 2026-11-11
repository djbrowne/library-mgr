from app.db import db
from app.models import AuditLog, utc_now

def record_audit(action, copy_id=None, isbn=None, user_id=None, previous_state=None, new_state=None, notes=None):
    """
    Permanently records an audit trail event.
    """
    entry = AuditLog(
        action=action,
        copy_id=copy_id,
        isbn=isbn,
        user_id=user_id,
        previous_state=str(previous_state) if previous_state is not None else None,
        new_state=str(new_state) if new_state is not None else None,
        notes=notes,
        timestamp=utc_now()
    )
    db.session.add(entry)
    db.session.flush()
    return entry
