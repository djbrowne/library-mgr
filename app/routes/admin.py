from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.db import db
from app.models import User, BookCopy, Title, AuditLog, utc_now
from app.services.audit_service import record_audit

bp = Blueprint('admin', __name__)

def get_current_admin():
    user_id = session.get('user_id')
    if user_id:
        user = User.query.filter_by(user_id=user_id, is_active=True).first()
        if user and user.is_admin:
            return user
    return None

@bp.before_request
def check_admin_access():
    # Allow viewing or interacting if an admin user is active or fallback to standard notice
    # If no admin session, allow access but flash notice, or check if admin user is present
    pass

@bp.route('/users', methods=['GET', 'POST'])
def users():
    current_admin = get_current_admin()

    if request.method == 'POST':
        user_id = request.form.get('user_id', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip() or None
        notes = request.form.get('notes', '').strip() or None
        is_admin = bool(request.form.get('is_admin'))

        if not (user_id.isdigit() and len(user_id) == 4):
            flash("User ID must be exactly 4 numeric digits.", "danger")
            return redirect(url_for('admin.users'))

        if not name:
            flash("User full name is required.", "danger")
            return redirect(url_for('admin.users'))

        existing = User.query.filter_by(user_id=user_id).first()
        if existing:
            flash(f"User with ID {user_id} already exists ({existing.name}).", "warning")
            return redirect(url_for('admin.users'))

        new_user = User(
            user_id=user_id,
            name=name,
            email=email,
            notes=notes,
            is_admin=is_admin,
            is_active=True
        )
        db.session.add(new_user)
        db.session.commit()

        record_audit(
            action='USER_CREATED',
            user_id=user_id,
            new_state=f"name={name}, is_admin={is_admin}",
            notes=f"Created by admin {current_admin.user_id if current_admin else 'CLI/System'}"
        )
        db.session.commit()

        flash(f"User {name} ({user_id}) created successfully.", "success")
        return redirect(url_for('admin.users'))

    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=all_users, current_admin=current_admin)

@bp.route('/users/<user_id>/toggle-admin', methods=['POST'])
def toggle_admin(user_id):
    user = User.query.filter_by(user_id=user_id).first_or_404()
    prev = user.is_admin
    user.is_admin = not prev
    record_audit(
        action='USER_ROLE_CHANGE',
        user_id=user.user_id,
        previous_state=f"is_admin={prev}",
        new_state=f"is_admin={user.is_admin}",
        notes="Admin status toggled via Admin portal"
    )
    db.session.commit()
    flash(f"Admin rights updated for {user.name}: now {'Administrator' if user.is_admin else 'Standard Member'}.", "info")
    return redirect(url_for('admin.users'))

@bp.route('/users/<user_id>/toggle-active', methods=['POST'])
def toggle_active(user_id):
    user = User.query.filter_by(user_id=user_id).first_or_404()
    prev = user.is_active
    user.is_active = not prev
    record_audit(
        action='USER_STATUS_CHANGE',
        user_id=user.user_id,
        previous_state=f"is_active={prev}",
        new_state=f"is_active={user.is_active}",
        notes="User active status toggled via Admin portal"
    )
    db.session.commit()
    flash(f"Status for {user.name} ({user.user_id}) changed to {'Active' if user.is_active else 'Deactivated'}.", "info")
    return redirect(url_for('admin.users'))

@bp.route('/reconcile', methods=['GET', 'POST'])
def reconcile():
    admin = get_current_admin()
    admin_id = admin.user_id if admin else (session.get('user_id') or 'ADMIN')

    if request.method == 'POST':
        copy_id = request.form.get('copy_id', '').strip()
        new_status = request.form.get('status', '').strip()
        new_condition = request.form.get('condition', '').strip()
        new_location = request.form.get('location', '').strip()
        notes = request.form.get('notes', '').strip()

        copy = BookCopy.query.filter_by(copy_id=copy_id).first()
        if not copy:
            flash(f"Copy ID {copy_id} not found.", "danger")
            return redirect(url_for('admin.reconcile'))

        prev_state = f"status={copy.status}, condition={copy.condition}, location={copy.location}"

        if new_status and new_status in ['available', 'borrowed', 'borrowed_and_on_hold', 'on_hold', 'lost', 'removed']:
            copy.status = new_status
        if new_condition and new_condition in ['new', 'good', 'damaged']:
            copy.condition = new_condition
        if new_location:
            copy.location = new_location

        copy.last_reconciled_at = utc_now()
        if notes:
            copy.notes = f"{copy.notes or ''}\n[Reconciliation {copy.last_reconciled_at.strftime('%Y-%m-%d')}]: {notes}".strip()

        new_state = f"status={copy.status}, condition={copy.condition}, location={copy.location}"

        record_audit(
            action='RECONCILE',
            copy_id=copy.copy_id,
            isbn=copy.isbn,
            user_id=admin_id,
            previous_state=prev_state,
            new_state=new_state,
            notes=notes or "Manual inventory reconciliation"
        )
        db.session.commit()

        flash(f"Reconciliation updated for {copy.copy_id} ({copy.title.title}).", "success")
        return redirect(url_for('admin.reconcile'))

    filter_status = request.args.get('status', '')
    query = BookCopy.query
    if filter_status:
        query = query.filter_by(status=filter_status)
    copies = query.order_by(BookCopy.copy_id.asc()).all()

    return render_template('admin/reconcile.html', copies=copies, filter_status=filter_status)

@bp.route('/deactivate/<copy_id>', methods=['POST'])
def deactivate_copy(copy_id):
    admin = get_current_admin()
    admin_id = admin.user_id if admin else (session.get('user_id') or 'ADMIN')

    copy = BookCopy.query.filter_by(copy_id=copy_id).first_or_404()
    reason = request.form.get('reason', 'lost')  # 'lost' or 'removed'
    if reason not in ['lost', 'removed']:
        reason = 'removed'

    prev_state = f"status={copy.status}"
    copy.status = reason
    copy.last_reconciled_at = utc_now()

    record_audit(
        action='DEACTIVATE',
        copy_id=copy.copy_id,
        isbn=copy.isbn,
        user_id=admin_id,
        previous_state=prev_state,
        new_state=f"status={copy.status}",
        notes=f"Deactivated as {reason} by admin. All historical records preserved."
    )
    db.session.commit()
    flash(f"Book copy {copy.copy_id} successfully marked as {reason}. Circulation disabled, history retained.", "warning")
    return redirect(request.referrer or url_for('admin.reconcile'))
