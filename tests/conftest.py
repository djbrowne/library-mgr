import pytest
from app import create_app
from app.config import TestConfig
from app.db import db
from app.models import User, Title, BookCopy, utc_now

@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        # Create test admin & member
        admin = User(user_id="0001", name="Admin User", email="admin@test.local", is_admin=True)
        member = User(user_id="1001", name="Alice Member", email="alice@test.local", is_admin=False)
        db.session.add_all([admin, member])

        # Create sample book with 2 copies
        t = Title(
            isbn="9780132350884",
            title="Clean Code",
            authors="Robert C. Martin",
            publisher="Prentice Hall",
            publish_year="2008"
        )
        db.session.add(t)
        db.session.flush()

        c1 = BookCopy(
            copy_id="9780132350884-1",
            isbn="9780132350884",
            copy_number=1,
            condition="new",
            status="available",
            location="Room 101 / Shelf A",
            registered_by="0001"
        )
        c2 = BookCopy(
            copy_id="9780132350884-2",
            isbn="9780132350884",
            copy_number=2,
            condition="good",
            status="available",
            location="Room 101 / Shelf B",
            registered_by="0001"
        )
        db.session.add_all([c1, c2])
        db.session.commit()

        yield app

        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()
