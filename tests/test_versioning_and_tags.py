import pytest
import json
from app.models import Title, Tag, BookTag
from app.db import db
from app.services.metadata_service import infer_genre_and_tags
from app.services.version_service import get_database_info, export_database, merge_database

def test_infer_genre_and_tags():
    # Test technology & software
    genre, tags = infer_genre_and_tags(
        categories=["Computers / Programming / Python"],
        subjects=["Software engineering", "Object-oriented design"],
        title="Python Clean Code"
    )
    assert genre == "Technology & Engineering"
    assert "computers" in tags
    assert "software-engineering" in tags

    # Test sci-fi
    genre_sf, tags_sf = infer_genre_and_tags(
        categories=["Fiction / Science Fiction"],
        subjects=["Space exploration", "Cyberpunk"],
        title="Neuromancer"
    )
    assert genre_sf == "Science Fiction"
    assert "cyberpunk" in tags_sf or "space-exploration" in tags_sf

def test_add_and_remove_tag_endpoints(app):
    client = app.test_client()

    # Add tag to Clean Code (9780132350884)
    res = client.post('/catalog/book/9780132350884/tags', json={'tag': 'software-craftsmanship'})
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert data['tag'] == 'software-craftsmanship'
    assert 'software-craftsmanship' in data['all_tags']

    # Verify persisted in database
    with app.app_context():
        title = Title.query.filter_by(isbn='9780132350884').first()
        assert 'software-craftsmanship' in title.tags_list

    # Add second tag
    res2 = client.post('/catalog/book/9780132350884/tags', json={'tag': 'agile'})
    assert res2.status_code == 200

    # Delete first tag
    del_res = client.post('/catalog/book/9780132350884/tags/software-craftsmanship/delete')
    assert del_res.status_code == 200
    del_data = del_res.get_json()
    assert del_data['success'] is True
    assert 'software-craftsmanship' not in del_data['all_tags']
    assert 'agile' in del_data['all_tags']

def test_update_genre_endpoint(app):
    client = app.test_client()

    res = client.post('/catalog/book/9780132350884/genre', json={'genre': 'Technology & Engineering'})
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert data['genre'] == 'Technology & Engineering'

    with app.app_context():
        t = Title.query.filter_by(isbn='9780132350884').first()
        assert t.genre == 'Technology & Engineering'

def test_search_by_genre_and_tag(app):
    client = app.test_client()

    # Assign genre and tag
    with app.app_context():
        t = Title.query.filter_by(isbn='9780132350884').first()
        t.genre = 'Technology & Engineering'
        tag = Tag(name='testing-tag')
        db.session.add(tag)
        db.session.flush()
        bt = BookTag(isbn='9780132350884', tag_id=tag.tag_id, is_auto_generated=False)
        db.session.add(bt)
        db.session.commit()

    # Search with matching genre
    res = client.get('/catalog/?genre=Technology%20%26%20Engineering')
    assert res.status_code == 200
    assert b'Clean Code' in res.data

    # Search with non-matching genre
    res_miss = client.get('/catalog/?genre=Mystery%20%26%20Thriller')
    assert res_miss.status_code == 200
    assert b'Clean Code' not in res_miss.data

    # Search with tag filter
    res_tag = client.get('/catalog/?tag=testing-tag')
    assert res_tag.status_code == 200
    assert b'Clean Code' in res_tag.data

def test_database_export_and_merge(app):
    with app.app_context():
        export_payload = export_database()
        assert 'titles' in export_payload
        assert 'book_copies' in export_payload
        assert 'users' in export_payload
        assert len(export_payload['titles']) >= 1

        # Simulate merge with an external instance containing a new title and copy
        merge_payload = {
            'users': [{'user_id': '2001', 'name': 'External User', 'is_admin': False}],
            'titles': [{
                'isbn': '9780201616224',
                'title': 'The Pragmatic Programmer',
                'authors': 'David Thomas, Andrew Hunt',
                'genre': 'Technology & Engineering',
                'tags': ['pragmatic', 'software']
            }],
            'book_copies': [{
                'copy_id': '9780201616224-1',
                'isbn': '9780201616224',
                'copy_number': 1,
                'condition': 'good',
                'status': 'available'
            }]
        }

        stats = merge_database(merge_payload, conflict_resolution="skip")
        assert stats['users_created'] == 1
        assert stats['titles_created'] == 1
        assert stats['copies_added'] == 1
        assert stats['tags_merged'] >= 1

        # Check imported title
        imported_title = Title.query.filter_by(isbn='9780201616224').first()
        assert imported_title is not None
        assert imported_title.genre == 'Technology & Engineering'
        assert 'pragmatic' in imported_title.tags_list
