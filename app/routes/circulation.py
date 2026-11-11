from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from app.services.circulation_service import checkout_book, checkin_book, place_hold
from app.models import BookCopy, Hold, Loan, Title, User

bp = Blueprint('circulation', __name__)

@bp.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if request.method == 'POST':
        user_id = request.form.get('user_id', '').strip()
        identifier = request.form.get('identifier', '').strip()

        if not user_id:
            user_id = session.get('user_id', '')

        success, msg, loan, copy = checkout_book(user_id, identifier)
        if success:
            flash(msg, 'success')
            return redirect(url_for('circulation.checkout'))
        else:
            flash(msg, 'danger')

    recent_checkouts = Loan.query.filter_by(status='active').order_by(Loan.checkout_date.desc()).limit(8).all()
    return render_template('circulation/checkout.html', recent_checkouts=recent_checkouts)

@bp.route('/checkin', methods=['GET', 'POST'])
def checkin():
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        condition_override = request.form.get('condition_override', '').strip() or None
        notes = request.form.get('notes', '').strip() or None

        success, msg, loan, copy = checkin_book(identifier, condition_override=condition_override, return_notes=notes)
        if success:
            flash(msg, 'success')
            return redirect(url_for('circulation.checkin'))
        else:
            flash(msg, 'danger')

    recent_returns = Loan.query.filter_by(status='returned').order_by(Loan.returned_date.desc()).limit(8).all()
    return render_template('circulation/checkin.html', recent_returns=recent_returns)

@bp.route('/holds', methods=['GET', 'POST'])
def holds():
    if request.method == 'POST':
        user_id = request.form.get('user_id', '').strip()
        isbn = request.form.get('isbn', '').strip()
        if not user_id:
            user_id = session.get('user_id', '')

        success, msg = place_hold(user_id, isbn)
        if success:
            flash(msg, 'success')
            return redirect(url_for('circulation.holds'))
        else:
            flash(msg, 'danger')

    active_holds = Hold.query.filter_by(status='waiting').order_by(Hold.placed_at.asc()).all()
    return render_template('circulation/holds.html', active_holds=active_holds)

@bp.route('/api/checkout', methods=['POST'])
def api_checkout():
    data = request.get_json() or {}
    user_id = data.get('user_id', '').strip() or session.get('user_id', '')
    identifier = data.get('identifier', '').strip()
    success, msg, loan, copy = checkout_book(user_id, identifier)
    return jsonify({
        'success': success,
        'message': msg,
        'copy_id': copy.copy_id if copy else None,
        'title': copy.title.title if copy and copy.title else None
    })

@bp.route('/api/checkin', methods=['POST'])
def api_checkin():
    data = request.get_json() or {}
    identifier = data.get('identifier', '').strip()
    condition = data.get('condition')
    notes = data.get('notes')
    success, msg, loan, copy = checkin_book(identifier, condition_override=condition, return_notes=notes)
    return jsonify({
        'success': success,
        'message': msg,
        'copy_id': copy.copy_id if copy else None,
        'title': copy.title.title if copy and copy.title else None,
        'status': copy.status if copy else None
    })
