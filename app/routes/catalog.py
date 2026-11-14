from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, current_app
from app.db import db
from app.models import Title, BookCopy, User, Hold, Tag, BookTag, DEFAULT_GENRES, utc_now
from app.services.metadata_service import clean_isbn, fetch_book_metadata, fetch_book_description, clean_tag_name
from app.services.audit_service import record_audit

bp = Blueprint('catalog', __name__)

@bp.route('/')
def search():
    query = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()
    condition_filter = request.args.get('condition', '').strip()
    genre_filter = request.args.get('genre', '').strip()
    tag_filter = request.args.get('tag', '').strip()

    titles_query = Title.query

    if query:
        search_term = query.lstrip('#').strip()
        clean = clean_isbn(search_term)
        conditions = [
            Title.title.ilike(f"%{search_term}%"),
            Title.authors.ilike(f"%{search_term}%"),
            Title.genre.ilike(f"%{search_term}%"),
            Title.book_tags.any(BookTag.tag.has(Tag.name.ilike(f"%{search_term}%")))
        ]
        if clean:
            conditions.append(Title.isbn.like(f"%{clean}%"))
        titles_query = titles_query.filter(db.or_(*conditions))

    if genre_filter:
        titles_query = titles_query.filter(Title.genre == genre_filter)

    if tag_filter:
        clean_tag_filter = tag_filter.lstrip('#').strip().lower()
        titles_query = titles_query.filter(Title.book_tags.any(BookTag.tag.has(Tag.name == clean_tag_filter)))

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

    # Get all distinct genres and popular tags for filter suggestions
    all_tags = Tag.query.order_by(Tag.name.asc()).all()

    return render_template(
        'catalog/search.html',
        results=results,
        query=query,
        status_filter=status_filter,
        condition_filter=condition_filter,
        genre_filter=genre_filter,
        tag_filter=tag_filter,
        genres=DEFAULT_GENRES,
        all_tags=all_tags
    )

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

@bp.route('/lookup-description')
def lookup_description():
    """Separate endpoint to specifically query/re-fetch book description."""
    isbn = request.args.get('isbn', '').strip()
    title = request.args.get('title', '').strip()
    authors = request.args.get('authors', '').strip()
    clean = clean_isbn(isbn)
    desc = fetch_book_description(clean, title=title, authors=authors)
    return jsonify({'description': desc or ''})

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
        cover_path = request.form.get('cover_image_path', '').strip() or None
        genre = request.form.get('genre', '').strip()
        tags_str = request.form.get('tags', '').strip()

        if not title:
            # If metadata not manually provided in form, fetch it
            if not title_text or not genre or not tags_str:
                meta = fetch_book_metadata(clean)
                if not title_text:
                    title_text = meta.get('title', f"Book (ISBN: {clean})")
                    authors_text = meta.get('authors', 'Unknown Author')
                    desc_text = meta.get('description', '')
                    publisher_text = meta.get('publisher', '')
                    publish_year_text = meta.get('publish_year', '')
                if not cover_path:
                    cover_path = meta.get('cover_image_path')
                if not genre:
                    genre = meta.get('genre', 'General')
                if not tags_str and meta.get('tags'):
                    tags_str = ", ".join(meta.get('tags'))

            # Ensure cover image is linked if it exists locally or can be fetched
            if not cover_path:
                covers_dir = current_app.config.get('COVERS_DIR')
                if covers_dir and (covers_dir / f"{clean}.jpg").exists():
                    cover_path = f"covers/{clean}.jpg"
                else:
                    meta = fetch_book_metadata(clean)
                    cover_path = meta.get('cover_image_path')

            title = Title(
                isbn=clean,
                title=title_text,
                authors=authors_text,
                description=desc_text,
                publisher=publisher_text,
                publish_year=publish_year_text,
                cover_image_path=cover_path,
                genre=genre or 'General'
            )
            db.session.add(title)
            db.session.flush()

            # Attach initial tags
            if tags_str:
                for raw_t in tags_str.split(','):
                    c_tag = clean_tag_name(raw_t)
                    if c_tag:
                        t_obj = Tag.query.filter_by(name=c_tag).first()
                        if not t_obj:
                            t_obj = Tag(name=c_tag)
                            db.session.add(t_obj)
                            db.session.flush()
                        bt = BookTag(isbn=clean, tag_id=t_obj.tag_id, added_by=user.user_id, is_auto_generated=False)
                        db.session.add(bt)
        else:
            # If title exists but lacks cover art, attach cover if available
            if not title.cover_image_path:
                covers_dir = current_app.config.get('COVERS_DIR')
                if covers_dir and (covers_dir / f"{clean}.jpg").exists():
                    title.cover_image_path = f"covers/{clean}.jpg"
                elif cover_path:
                    title.cover_image_path = cover_path
                else:
                    meta = fetch_book_metadata(clean)
                    if meta.get('cover_image_path'):
                        title.cover_image_path = meta.get('cover_image_path')
            if genre and (not title.genre or title.genre == 'General'):
                title.genre = genre

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

    return render_template('catalog/register.html', genres=DEFAULT_GENRES)

@bp.route('/book/<isbn>')
def detail(isbn):
    clean = clean_isbn(isbn)
    title = Title.query.filter_by(isbn=clean).first_or_404()
    copies = title.copies.order_by(BookCopy.copy_number.asc()).all()
    holds = title.holds.order_by(Hold.placed_at.asc()).all()
    return render_template('catalog/detail.html', title=title, copies=copies, holds=holds, genres=DEFAULT_GENRES)

@bp.route('/book/<isbn>/tags', methods=['POST'])
def add_tag(isbn):
    """Add a free-form tag to a book (open to all users)."""
    clean = clean_isbn(isbn)
    title = Title.query.filter_by(isbn=clean).first_or_404()
    data = request.get_json(silent=True) or request.form
    raw_tag = data.get('tag', '').strip()
    tag_name = clean_tag_name(raw_tag)

    if not tag_name:
        return jsonify({'error': 'Tag must be between 3 and 30 alphanumeric characters'}), 400

    user_id = session.get('user_id') or (data.get('user_id', '').strip() if data.get('user_id') else None)

    tag = Tag.query.filter_by(name=tag_name).first()
    if not tag:
        tag = Tag(name=tag_name)
        db.session.add(tag)
        db.session.flush()

    existing = BookTag.query.filter_by(isbn=clean, tag_id=tag.tag_id).first()
    if not existing:
        bt = BookTag(isbn=clean, tag_id=tag.tag_id, added_by=user_id, is_auto_generated=False)
        db.session.add(bt)
        db.session.commit()

    return jsonify({
        'success': True,
        'tag': tag.name,
        'tag_id': tag.tag_id,
        'all_tags': title.tags_list
    })

@bp.route('/book/<isbn>/tags/<tag_name>/delete', methods=['POST', 'DELETE'])
@bp.route('/book/<isbn>/tags/<tag_name>', methods=['DELETE'])
def delete_tag(isbn, tag_name):
    """Remove a tag association from a book."""
    clean = clean_isbn(isbn)
    title = Title.query.filter_by(isbn=clean).first_or_404()
    clean_name = tag_name.lower().strip()

    tag = Tag.query.filter_by(name=clean_name).first()
    if tag:
        bt = BookTag.query.filter_by(isbn=clean, tag_id=tag.tag_id).first()
        if bt:
            db.session.delete(bt)
            db.session.commit()
            return jsonify({'success': True, 'all_tags': title.tags_list})

    return jsonify({'error': 'Tag not associated with this book'}), 404

@bp.route('/book/<isbn>/genre', methods=['POST'])
def update_genre(isbn):
    """Update a book's genre."""
    clean = clean_isbn(isbn)
    title = Title.query.filter_by(isbn=clean).first_or_404()
    data = request.get_json(silent=True) or request.form
    genre = data.get('genre', '').strip()

    if genre:
        title.genre = genre
        db.session.commit()
        return jsonify({'success': True, 'genre': title.genre})
    return jsonify({'error': 'Genre cannot be blank'}), 400
