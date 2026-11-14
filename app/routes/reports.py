import csv
import io
from flask import Blueprint, render_template, request, Response
from app.db import db
from app.models import Loan, BookCopy, Title, User, AuditLog, Tag, BookTag
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

@bp.route('/tags')
def tag_report():
    """Tag & Genre analytics and drill-down report."""
    selected_tag_name = request.args.get('tag', '').strip().lower()
    search_q = request.args.get('q', '').strip().lower()

    # Query all tags
    tags_query = Tag.query
    if search_q:
        tags_query = tags_query.filter(Tag.name.ilike(f"%{search_q}%"))
    all_tags = tags_query.order_by(Tag.name.asc()).all()

    tag_stats = []
    for tag in all_tags:
        bts = tag.book_tags.all()
        titles = list({bt.title for bt in bts if bt.title})
        total_copies = sum(t.total_copies_count for t in titles)
        available_copies = sum(t.available_copies_count for t in titles)
        user_added = sum(1 for bt in bts if not bt.is_auto_generated)
        auto_gen = sum(1 for bt in bts if bt.is_auto_generated)

        tag_stats.append({
            'tag': tag,
            'titles_count': len(titles),
            'total_copies': total_copies,
            'available_copies': available_copies,
            'user_added_count': user_added,
            'auto_generated_count': auto_gen
        })

    # Sort tag_stats by titles_count descending, then name ascending
    tag_stats.sort(key=lambda x: (-x['titles_count'], x['tag'].name))

    # Selected tag drill-down details
    selected_tag = None
    selected_titles = []
    if selected_tag_name:
        selected_tag = Tag.query.filter_by(name=selected_tag_name).first()
        if selected_tag:
            selected_bts = selected_tag.book_tags.all()
            selected_titles = list({bt.title for bt in selected_bts if bt.title})
            selected_titles.sort(key=lambda t: t.title)

    # Untagged books report
    untagged_titles = Title.query.filter(~Title.book_tags.any()).order_by(Title.title.asc()).all()

    # Genre breakdown
    genre_counts = {}
    for title in Title.query.all():
        g = title.genre or 'General'
        genre_counts[g] = genre_counts.get(g, 0) + 1
    genre_stats = sorted(genre_counts.items(), key=lambda x: -x[1])

    # Summary metrics
    total_tags_count = Tag.query.count()
    total_titles_count = Title.query.count()
    tagged_titles_count = Title.query.filter(Title.book_tags.any()).count()
    most_popular_tag = tag_stats[0] if tag_stats else None

    return render_template(
        'reports/tags.html',
        tag_stats=tag_stats,
        selected_tag=selected_tag,
        selected_tag_name=selected_tag_name,
        selected_titles=selected_titles,
        untagged_titles=untagged_titles,
        genre_stats=genre_stats,
        total_tags_count=total_tags_count,
        total_titles_count=total_titles_count,
        tagged_titles_count=tagged_titles_count,
        most_popular_tag=most_popular_tag,
        search_q=search_q
    )

@bp.route('/tags/export.csv')
def export_tags_csv():
    """Export tag analytics and catalog mappings to CSV."""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        'Tag',
        'ISBN',
        'Title',
        'Authors',
        'Genre',
        'Total Copies',
        'Available Copies',
        'Added By User ID',
        'Tag Source',
        'Tag Created At'
    ])

    bts = BookTag.query.join(Tag).join(Title).order_by(Tag.name.asc(), Title.title.asc()).all()
    for bt in bts:
        writer.writerow([
            bt.tag.name,
            bt.isbn,
            bt.title.title if bt.title else '',
            bt.title.authors if bt.title else '',
            bt.title.genre if bt.title else 'General',
            bt.title.total_copies_count if bt.title else 0,
            bt.title.available_copies_count if bt.title else 0,
            bt.added_by or 'System',
            'Auto-extracted' if bt.is_auto_generated else 'User-assigned',
            bt.created_at.strftime('%Y-%m-%d %H:%M:%S') if bt.created_at else ''
        ])

    csv_data = output.getvalue()
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=library_tags_report.csv'}
    )
