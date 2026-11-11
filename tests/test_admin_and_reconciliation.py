from app.models import BookCopy, User, Loan, AuditLog, utc_now
from app.services.circulation_service import checkout_book

def test_admin_reconciliation(client, app):
    with app.app_context():
        # Reconcile copy 1: change condition to damaged, change location
        resp = client.post('/admin/reconcile', data={
            'copy_id': '9780132350884-1',
            'status': 'available',
            'condition': 'damaged',
            'location': 'Repair Shelf / Workshop',
            'notes': 'Spine cracked during handling'
        }, follow_redirects=True)
        assert resp.status_code == 200

        copy = BookCopy.query.filter_by(copy_id='9780132350884-1').first()
        assert copy.condition == 'damaged'
        assert copy.location == 'Repair Shelf / Workshop'
        assert copy.last_reconciled_at is not None

        # Verify audit log entry was created
        log = AuditLog.query.filter_by(action='RECONCILE', copy_id='9780132350884-1').first()
        assert log is not None
        assert 'damaged' in log.new_state
        assert 'Spine cracked' in log.notes

def test_deactivate_lost_book_keeps_history(client, app):
    with app.app_context():
        # First checkout and return to generate historical records
        checkout_book('1001', '9780132350884-2')

        # Now deactivate as lost via admin endpoint
        resp = client.post('/admin/deactivate/9780132350884-2', data={'reason': 'lost'}, follow_redirects=True)
        assert resp.status_code == 200

        copy = BookCopy.query.filter_by(copy_id='9780132350884-2').first()
        assert copy.status == 'lost'

        # Attempting checkout must fail
        success, msg, loan, _ = checkout_book('1001', '9780132350884-2')
        assert success is False
        assert "marked as lost" in msg

        # Prior loans and audit history must still be 100% intact
        past_loans = Loan.query.filter_by(copy_id='9780132350884-2').all()
        assert len(past_loans) >= 1

        deactivate_log = AuditLog.query.filter_by(action='DEACTIVATE', copy_id='9780132350884-2').first()
        assert deactivate_log is not None

def test_user_management_web_flow(client, app):
    with app.app_context():
        # Add new user via form
        resp = client.post('/admin/users', data={
            'user_id': '3333',
            'name': 'Test Librarian',
            'email': 'librarian@test.local',
            'notes': 'Lead cataloger',
            'is_admin': 'on'
        }, follow_redirects=True)
        assert resp.status_code == 200

        u = User.query.filter_by(user_id='3333').first()
        assert u is not None
        assert u.name == 'Test Librarian'
        assert u.is_admin is True

        # Toggle admin privilege
        client.post('/admin/users/3333/toggle-admin', follow_redirects=True)
        u = User.query.filter_by(user_id='3333').first()
        assert u.is_admin is False

        # Toggle active status
        client.post('/admin/users/3333/toggle-active', follow_redirects=True)
        u = User.query.filter_by(user_id='3333').first()
        assert u.is_active is False
