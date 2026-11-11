from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from app.db import db
from app.models import Title, BookCopy, User, Hold, utc_now
from app.services.metadata_service import clean_isbn, fetch_book_metadata
from app.services.audit_service import record_audit

bp = Blueprint('catalog', __name__)

@bp.route('/')
def search():
    query = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()
    condition_filter = request.args.get('condition', '').strip()

    titles_query = Title.query

    if query:
        clean = clean_isbn(query)
        if clean:
            titles_query = titles_query.filter(
                (Title.isbn.like(f"%{clean}%")) |
                (Title.title.ilike(f"%{query}%")) |
                (Title.authors.ilike(f"%{query}%"))
            )
        else:
            titles_query = titles_query.filter(
                (Title.title.ilike(f"%{query}%")) |
                (Title.authors.ilike(f"%{query}%"))
            )

    titles = titles_query.order_by(Title.title.asc()).all()

    # Apply copy-level filters if selected
    results = []
    for t in titles:
        copies = t.copies.all()
        if status_filter:
            copies = [c for c in copies if c.status == status_filter]
        if condition_filter:
            copies = [c for c in copies if c.condition == condition_filter]

        if not (status_filter or condition_filter) or copies:
            results.append({
                'title': t,
                'copies': copies
            })

    return render_template('catalog/search.html', results=results, query=query, status_filter=status_filter, condition_filter=condition_filter)

@bp.route('/lookup-isbn')
def lookup_isbn():
    isbn = request.args.get('isbn', '').strip()
    clean = clean_isbn(isbn)
    if not clean:
        return jsonify({'error': 'Invalid ISBN'}), 400

    data = fetch_book_metadata(clean)
    existing_title = Title.query.filter_by(isbn=clean).first()
    data['already_in_catalog'] = existing_title is not None
    data['existing_copies_count'] = existing_title.copies.count() if existing_title else 0
    return jsonify(data)

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        isbn = request.form.get('isbn', '').strip()
        clean = clean_isbn(isbn)
        user_id = request.form.get('user_id', '').strip() or session.get('user_id')
        condition = request.form.get('condition', 'good').strip()
        location = request.form.get('location', 'Main Room / Shelf A').strip()
        notes = request.form.get('notes', '').strip()
        title_text = request.form.get('title', '').strip()
        authors_text = request.form.get('authors', '').strip()
        desc_text = request.form.get('description', '').strip()
        publisher_text = request.form.get('publisher', '').strip()
        publish_year_text = request.form.get('publish_year', '').strip()

        if not clean:
            flash("Valid ISBN is required.", "danger")
            return redirect(url_for('catalog.register'))

        if not user_id:
            flash("User ID of registrar is required.", "danger")
            return redirect(url_for('catalog.register'))

        user = User.query.filter_by(user_id=user_id, is_active=True).first()
        if not user:
            flash(f"Registrar User ID '{user_id}' does not exist.", "danger")
            return redirect(url_for('catalog.register'))

        # Check or fetch title
        title = Title.query.filter_by(isbn=clean).first()
        if not title:
            # If metadata not manually provided in form, fetch it
            if not title_text:
                meta = fetch_book_metadata(clean)
                title_text = meta.get('title', f"Book (ISBN: {clean})")
                authors_text = meta.get('authors', 'Unknown Author')
                desc_text = meta.get('description', '')
                publisher_text = meta.get('publisher', '')
                publish_year_text = meta.get('publish_year', '')
                cover_path = meta.get('cover_image_path')
            else:
                cover_path = None

            title = Title(
                isbn=clean,
                title=title_text,
                authors=authors_text,
                description=desc_text,
                publisher=publisher_text,
                publish_year=publish_year_text,
                cover_image_path=cover_path
            )
            db.session.add(title)
            db.session.flush()

        # Determine next copy number (e.g. ISBN-1, ISBN-2)
        existing_copies = title.copies.all()
        next_copy_num = len(existing_copies) + 1
        copy_id = f"{clean}-{next_copy_num}"

        copy = BookCopy(
            copy_id=copy_id,
            isbn=clean,
            copy_number=next_copy_num,
            condition=condition if condition in ['new', 'good', 'damaged'] else 'good',
            status='available',
            location=location or 'Main Room / Shelf A',
            registered_by=user.user_id,
            registered_at=utc_now(),
            notes=notes
        )
        db.session.add(copy)
        db.session.flush()

        record_audit(
            action='REGISTER',
            copy_id=copy.copy_id,
            isbn=clean,
            user_id=user.user_id,
            new_state=f"status=available, condition={copy.condition}, location={copy.location}",
            notes=f"Registered copy {copy.copy_id} by {user.name} ({user.user_id})"
        )

        db.session.commit()
        flash(f"Successfully registered copy '{copy.copy_id}' of '{title.title}'!", "success")
        return redirect(url_for('catalog.detail', isbn=clean))

    return render_template('catalog/register.html')

@bp.route('/book/<isbn>')
def detail(isbn):
    clean = clean_isbn(isbn)
    title = Title.query.filter_by(isbn=clean).first_or_404()
    copies = title.copies.order_by(BookCopy.copy_number.asc()).all()
    holds = title.holds.order_by(Hold.placed_at.asc()).all()
    return render_template('catalog/detail.html', title=title, copies=copies, holds=holds)
