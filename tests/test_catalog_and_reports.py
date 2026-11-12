from app.models import Title, BookCopy, User
from app.services.circulation_service import checkout_book

def test_book_registration_and_copy_increment(client, app):
    with app.app_context():
        # Register a new title with ISBN 9780201616224
        resp = client.post('/catalog/register', data={
            'isbn': '9780201616224',
            'title': 'The Pragmatic Programmer',
            'authors': 'Andrew Hunt, David Thomas',
            'condition': 'new',
            'location': 'Room 101 / Shelf C',
            'user_id': '0001',
            'notes': 'First copy registered'
        }, follow_redirects=True)
        assert resp.status_code == 200

        title = Title.query.filter_by(isbn='9780201616224').first()
        assert title is not None
        assert title.copies.count() == 1
        assert title.copies.first().copy_id == '9780201616224-1'

        # Register a second copy of same ISBN
        resp2 = client.post('/catalog/register', data={
            'isbn': '9780201616224',
            'condition': 'good',
            'location': 'Room 101 / Shelf C',
            'user_id': '0001',
            'notes': 'Second copy registered'
        }, follow_redirects=True)
        assert resp2.status_code == 200

        assert title.copies.count() == 2
        copies = [c.copy_id for c in title.copies.all()]
        assert '9780201616224-1' in copies
        assert '9780201616224-2' in copies

def test_reports_endpoints(client, app):
    with app.app_context():
        # Check out book so active loans has data
        checkout_book('1001', '9780132350884-1')

        # Test active loans report
        r1 = client.get('/reports/active-loans')
        assert r1.status_code == 200
        assert b"9780132350884-1" in r1.data

        # Test condition report
        r2 = client.get('/reports/condition')
        assert r2.status_code == 200
        assert b"Books by Condition" in r2.data

        # Test book history
        r3 = client.get('/reports/book-history?identifier=9780132350884-1')
        assert r3.status_code == 200
        assert b"Clean Code" in r3.data

        # Test user history
        r4 = client.get('/reports/user-history?user_id=1001')
        assert r4.status_code == 200
        assert b"Alice Member" in r4.data

        # Test audit log report
        r5 = client.get('/reports/audit-log')
        assert r5.status_code == 200
        assert b"Permanent Audit Trail" in r5.data

def test_cover_art_persistence_on_registration(client, app):
    with app.app_context():
        # Register a book passing cover_image_path
        resp = client.post('/catalog/register', data={
            'isbn': '9780134494166',
            'title': 'Clean Architecture',
            'authors': 'Robert C. Martin',
            'cover_image_path': 'covers/9780134494166.jpg',
            'user_id': '0001',
            'condition': 'new'
        }, follow_redirects=True)
        assert resp.status_code == 200

        title = Title.query.filter_by(isbn='9780134494166').first()
        assert title is not None
        assert title.cover_image_path == 'covers/9780134494166.jpg'
        assert title.display_cover_path == 'covers/9780134494166.jpg'

def test_lookup_description_endpoint(client, app):
    # Test looking up description separately via API endpoint
    res = client.get('/catalog/lookup-description?isbn=9780132350884&title=Clean+Code')
    assert res.status_code == 200
    data = res.get_json()
    assert 'description' in data
    assert isinstance(data['description'], str)
