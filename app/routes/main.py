from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.models import User, Title, BookCopy, Loan, Hold

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    total_titles = Title.query.count()
    total_copies = BookCopy.query.filter(BookCopy.status != 'removed').count()
    borrowed_count = BookCopy.query.filter(BookCopy.status.in_(['borrowed', 'borrowed_and_on_hold'])).count()
    available_count = BookCopy.query.filter_by(status='available').count()
    damaged_count = BookCopy.query.filter_by(condition='damaged').count()
    waiting_holds = Hold.query.filter_by(status='waiting').count()

    recent_loans = Loan.query.order_by(Loan.checkout_date.desc()).limit(6).all()
    recent_titles = Title.query.order_by(Title.created_at.desc()).limit(6).all()

    return render_template(
        'index.html',
        total_titles=total_titles,
        total_copies=total_copies,
        borrowed_count=borrowed_count,
        available_count=available_count,
        damaged_count=damaged_count,
        waiting_holds=waiting_holds,
        recent_loans=recent_loans,
        recent_titles=recent_titles
    )

@bp.route('/set-user', methods=['POST'])
def set_user():
    user_id = request.form.get('user_id', '').strip()
    if not (user_id.isdigit() and len(user_id) == 4):
        flash("User ID must be exactly 4 numeric digits.", "danger")
        return redirect(request.referrer or url_for('main.index'))

    user = User.query.filter_by(user_id=user_id, is_active=True).first()
    if not user:
        flash(f"User ID {user_id} was not found or is inactive.", "warning")
    else:
        session['user_id'] = user.user_id
        role = "Administrator" if user.is_admin else "Library Member"
        flash(f"Active user set to: {user.name} ({user.user_id}) - {role}", "success")

    return redirect(request.referrer or url_for('main.index'))

@bp.route('/clear-user')
def clear_user():
    session.pop('user_id', None)
    flash("User session cleared.", "info")
    return redirect(request.referrer or url_for('main.index'))
