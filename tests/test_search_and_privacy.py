from app.models import AuditLog, Title, BookCopy

def test_user_search_privacy(client, app):
    with app.app_context():
        # Count audit log entries prior to search
        initial_log_count = AuditLog.query.count()

        # Perform searches in catalog
        client.get('/catalog/?q=Clean+Code')
        client.get('/catalog/?q=Robert+Martin&status=available')
        client.get('/catalog/?q=9780132350884')

        # Requirement 15: Tracking of book movement and user history saved permanently, BUT NOT user searches
        after_log_count = AuditLog.query.count()
        assert after_log_count == initial_log_count, "User searches must not be recorded into audit_logs"

def test_search_filters(client, app):
    with app.app_context():
        # Search by author
        resp1 = client.get('/catalog/?q=Martin')
        assert b"Clean Code" in resp1.data

        # Search by condition
        resp2 = client.get('/catalog/?condition=new')
        assert b"Clean Code" in resp2.data

        # Search non-existing
        resp3 = client.get('/catalog/?q=NonExistentBook12345')
        assert b"No Books Found" in resp3.data
