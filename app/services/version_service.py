import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import text
from app.db import db
from app.models import User, Title, BookCopy, Loan, Hold, AuditLog, utc_now

logger = logging.getLogger(__name__)

# Schema capabilities registry mapping revisions to semantic versions and feature lists
SCHEMA_CAPABILITIES = {
    '4d39cfdf595f': {
        'version': '1.0.0',
        'title': 'Core Library Circulation & Scanning',
        'capabilities': [
            '4-digit numeric User identity and role management',
            'ISBN cataloging with auto-increment multi-copy tracking',
            'Book condition tracking (new, good, damaged) and physical location',
            'Check-out, check-in, and auto-resolving single-copy returns',
            'Hold queue placement and fulfillment workflow',
            'Admin reconciliation with immutable audit trail',
            'Lost/removed book deactivation preserving historical circulation',
            'Real-time webcam & file barcode scanning (EAN-13 / ISBN-13)'
        ]
    },
    'a44124d7f9d6': {
        'version': '1.1.0',
        'title': 'Genre Categorization & Free-form Book Tagging',
        'capabilities': [
            'Standard & custom Book Genre categorization',
            'Normalized Tag vocabulary with many-to-many book association',
            'Best-effort automated genre/tag extraction from Open Library and Google Books',
            'Interactive user and admin tag creation and deletion',
            'Multi-instance database export, import, and reconciliation merge'
        ]
    }
}

def get_current_schema_revision():
    """Retrieve the current Alembic revision hash from the active database."""
    try:
        result = db.session.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
        return result
    except Exception as e:
        logger.warning(f"Could not read alembic_version table: {e}")
        return None

def get_database_info():
    """Return comprehensive schema version and capability status."""
    current_rev = get_current_schema_revision()
    cap_info = SCHEMA_CAPABILITIES.get(current_rev, {
        'version': 'unknown',
        'title': 'Custom or Unregistered Revision',
        'capabilities': []
    })

    # Accumulate all capabilities enabled up to this revision
    enabled_features = []
    # If 1.0.0 or later
    if current_rev:
        enabled_features.extend(SCHEMA_CAPABILITIES.get('4d39cfdf595f', {}).get('capabilities', []))
    if current_rev == 'a44124d7f9d6':
        enabled_features.extend(SCHEMA_CAPABILITIES.get('a44124d7f9d6', {}).get('capabilities', []))

    return {
        'revision': current_rev,
        'semantic_version': cap_info.get('version'),
        'milestone_title': cap_info.get('title'),
        'active_capabilities': enabled_features,
        'registered_milestones': SCHEMA_CAPABILITIES
    }

def export_database(output_path=None):
    """
    Export the current database catalog, users, copies, loans, holds, and tags into a portable dictionary or JSON file.
    """
    users = [u.to_dict() for u in User.query.all()]
    
    titles_data = []
    for t in Title.query.all():
        td = {
            'isbn': t.isbn,
            'title': t.title,
            'authors': t.authors,
            'description': t.description,
            'publisher': t.publisher,
            'publish_year': t.publish_year,
            'cover_image_path': t.cover_image_path,
            'genre': getattr(t, 'genre', None),
            'created_at': t.created_at.isoformat() if t.created_at else None,
            'tags': [bt.tag.name for bt in getattr(t, 'book_tags', [])] if hasattr(t, 'book_tags') else []
        }
        titles_data.append(td)

    copies_data = []
    for c in BookCopy.query.all():
        copies_data.append({
            'copy_id': c.copy_id,
            'isbn': c.isbn,
            'copy_number': c.copy_number,
            'condition': c.condition,
            'status': c.status,
            'location': c.location,
            'registered_by': c.registered_by,
            'registered_at': c.registered_at.isoformat() if c.registered_at else None,
            'last_reconciled_at': c.last_reconciled_at.isoformat() if c.last_reconciled_at else None,
            'notes': c.notes
        })

    loans_data = []
    for l in Loan.query.all():
        loans_data.append({
            'loan_id': l.loan_id,
            'copy_id': l.copy_id,
            'user_id': l.user_id,
            'checkout_date': l.checkout_date.isoformat() if l.checkout_date else None,
            'due_date': l.due_date.isoformat() if l.due_date else None,
            'returned_date': l.returned_date.isoformat() if l.returned_date else None,
            'return_condition': l.return_condition,
            'status': l.status
        })

    holds_data = []
    for h in Hold.query.all():
        holds_data.append({
            'hold_id': h.hold_id,
            'isbn': h.isbn,
            'user_id': h.user_id,
            'placed_at': h.placed_at.isoformat() if h.placed_at else None,
            'status': h.status
        })

    payload = {
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'schema_revision': get_current_schema_revision(),
        'version': get_database_info()['semantic_version'],
        'users': users,
        'titles': titles_data,
        'book_copies': copies_data,
        'loans': loans_data,
        'holds': holds_data
    }

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)

    return payload

def merge_database(payload_or_path, conflict_resolution="skip"):
    """
    Merge an exported database JSON or dictionary into the current database instance.
    Handles user de-duplication, title union, copy numbering offsets, and tag merging.
    """
    if isinstance(payload_or_path, (str, Path)):
        with open(payload_or_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = payload_or_path

    stats = {
        'users_created': 0,
        'users_updated': 0,
        'titles_created': 0,
        'titles_updated': 0,
        'copies_added': 0,
        'tags_merged': 0
    }

    # 1. Merge Users
    for udata in data.get('users', []):
        uid = str(udata.get('user_id', '')).zfill(4)
        user = User.query.filter_by(user_id=uid).first()
        if not user:
            user = User(
                user_id=uid,
                name=udata.get('name', 'Merged User'),
                email=udata.get('email'),
                is_admin=bool(udata.get('is_admin', False)),
                notes=udata.get('notes'),
                is_active=bool(udata.get('is_active', True))
            )
            db.session.add(user)
            stats['users_created'] += 1
        elif conflict_resolution == 'overwrite':
            user.name = udata.get('name', user.name)
            user.email = udata.get('email', user.email)
            user.notes = udata.get('notes', user.notes)
            stats['users_updated'] += 1

    db.session.flush()

    # 2. Merge Titles & Tags
    # Import Tag and BookTag dynamically if models have been migrated
    Tag = None
    BookTag = None
    try:
        from app.models import Tag as TagModel, BookTag as BookTagModel
        Tag = TagModel
        BookTag = BookTagModel
    except ImportError:
        pass

    for tdata in data.get('titles', []):
        isbn = str(tdata.get('isbn')).strip()
        title = Title.query.filter_by(isbn=isbn).first()
        if not title:
            title = Title(
                isbn=isbn,
                title=tdata.get('title', 'Unknown Title'),
                authors=tdata.get('authors'),
                description=tdata.get('description'),
                publisher=tdata.get('publisher'),
                publish_year=tdata.get('publish_year'),
                cover_image_path=tdata.get('cover_image_path')
            )
            if hasattr(title, 'genre') and tdata.get('genre'):
                title.genre = tdata.get('genre')
            db.session.add(title)
            stats['titles_created'] += 1
        else:
            if conflict_resolution == 'overwrite':
                title.title = tdata.get('title', title.title)
                title.authors = tdata.get('authors', title.authors)
                title.description = tdata.get('description', title.description)
                title.publisher = tdata.get('publisher', title.publisher)
                title.publish_year = tdata.get('publish_year', title.publish_year)
                if tdata.get('cover_image_path') and not title.cover_image_path:
                    title.cover_image_path = tdata.get('cover_image_path')
                if hasattr(title, 'genre') and tdata.get('genre'):
                    title.genre = tdata.get('genre')
                stats['titles_updated'] += 1

        db.session.flush()

        # Merge tags if supported
        if Tag and BookTag and tdata.get('tags'):
            for tag_name in tdata['tags']:
                clean_tag = tag_name.strip().lower()
                if not clean_tag:
                    continue
                tag_obj = Tag.query.filter_by(name=clean_tag).first()
                if not tag_obj:
                    tag_obj = Tag(name=clean_tag)
                    db.session.add(tag_obj)
                    db.session.flush()

                existing_bt = BookTag.query.filter_by(isbn=isbn, tag_id=tag_obj.tag_id).first()
                if not existing_bt:
                    bt = BookTag(isbn=isbn, tag_id=tag_obj.tag_id, is_auto_generated=False)
                    db.session.add(bt)
                    stats['tags_merged'] += 1

    # 3. Merge Book Copies
    for cdata in data.get('book_copies', []):
        isbn = str(cdata.get('isbn')).strip()
        copy_id = cdata.get('copy_id')
        existing_copy = BookCopy.query.filter_by(copy_id=copy_id).first()
        if not existing_copy:
            # Check if copy_id already exists or copy_number collides
            max_num = db.session.query(db.func.max(BookCopy.copy_number)).filter_by(isbn=isbn).scalar() or 0
            new_copy_num = max_num + 1
            new_copy_id = f"{isbn}-{new_copy_num}"

            copy = BookCopy(
                copy_id=new_copy_id,
                isbn=isbn,
                copy_number=new_copy_num,
                condition=cdata.get('condition', 'good'),
                status=cdata.get('status', 'available'),
                location=cdata.get('location', 'Main Room / Shelf A'),
                registered_by=cdata.get('registered_by'),
                notes=f"Merged instance record (orig copy_id: {copy_id})"
            )
            db.session.add(copy)
            stats['copies_added'] += 1

    db.session.commit()
    return stats
