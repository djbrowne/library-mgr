from datetime import datetime, timezone
from app.db import db

def utc_now():
    return datetime.now(timezone.utc)

DEFAULT_GENRES = [
    "Fiction",
    "Non-Fiction",
    "Science Fiction",
    "Fantasy",
    "Mystery & Thriller",
    "Biography & Memoir",
    "Technology & Engineering",
    "Science & Nature",
    "History",
    "Philosophy & Psychology",
    "Arts & Photography",
    "Children & Young Adult",
    "General"
]

class Tag(db.Model):
    __tablename__ = 'tags'

    tag_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    book_tags = db.relationship('BookTag', back_populates='tag', cascade='all, delete-orphan', lazy='dynamic')

    def to_dict(self):
        return {
            'tag_id': self.tag_id,
            'name': self.name,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class BookTag(db.Model):
    __tablename__ = 'book_tags'
    __table_args__ = (
        db.UniqueConstraint('isbn', 'tag_id', name='uq_book_tag'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    isbn = db.Column(db.String(20), db.ForeignKey('titles.isbn'), nullable=False, index=True)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.tag_id'), nullable=False, index=True)
    added_by = db.Column(db.String(4), db.ForeignKey('users.user_id'), nullable=True)
    is_auto_generated = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    title = db.relationship('Title', back_populates='book_tags')
    tag = db.relationship('Tag', back_populates='book_tags')
    user = db.relationship('User')

class User(db.Model):
    __tablename__ = 'users'

    user_id = db.Column(db.String(4), primary_key=True)  # 4-digit ID
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    loans = db.relationship('Loan', back_populates='user', lazy='dynamic')
    holds = db.relationship('Hold', back_populates='user', lazy='dynamic')

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'name': self.name,
            'email': self.email,
            'is_admin': self.is_admin,
            'notes': self.notes,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Title(db.Model):
    __tablename__ = 'titles'

    isbn = db.Column(db.String(20), primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    authors = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    publisher = db.Column(db.String(255), nullable=True)
    publish_year = db.Column(db.String(20), nullable=True)
    cover_image_path = db.Column(db.String(255), nullable=True)
    genre = db.Column(db.String(50), nullable=True, default='General')
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    copies = db.relationship('BookCopy', back_populates='title', cascade='all, delete-orphan', lazy='dynamic')
    holds = db.relationship('Hold', back_populates='title', cascade='all, delete-orphan', lazy='dynamic')
    book_tags = db.relationship('BookTag', back_populates='title', cascade='all, delete-orphan', lazy='joined')

    @property
    def tags_list(self):
        return [bt.tag.name for bt in self.book_tags]

    @property
    def available_copies_count(self):
        return self.copies.filter_by(status='available').count()

    @property
    def total_copies_count(self):
        return self.copies.filter(BookCopy.status.notin_(['removed'])).count()

    @property
    def display_cover_path(self):
        if self.cover_image_path:
            return self.cover_image_path
        try:
            from flask import current_app
            covers_dir = current_app.config.get('COVERS_DIR')
            if covers_dir and (covers_dir / f"{self.isbn}.jpg").exists():
                return f"covers/{self.isbn}.jpg"
        except Exception:
            pass
        return None

class BookCopy(db.Model):
    __tablename__ = 'book_copies'

    copy_id = db.Column(db.String(30), primary_key=True)  # e.g., "9780132350884-1"
    isbn = db.Column(db.String(20), db.ForeignKey('titles.isbn'), nullable=False)
    copy_number = db.Column(db.Integer, nullable=False)
    condition = db.Column(db.String(20), default='good', nullable=False)  # new, good, damaged
    status = db.Column(db.String(35), default='available', nullable=False)  # available, borrowed, borrowed_and_on_hold, on_hold, lost, removed
    location = db.Column(db.String(100), default='Main Room / Shelf A', nullable=False)
    registered_by = db.Column(db.String(4), db.ForeignKey('users.user_id'), nullable=True)
    registered_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    last_reconciled_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    title = db.relationship('Title', back_populates='copies')
    registrar = db.relationship('User', foreign_keys=[registered_by])
    loans = db.relationship('Loan', back_populates='copy', cascade='all, delete-orphan', lazy='dynamic')

    @property
    def active_loan(self):
        return self.loans.filter_by(status='active').first()

class Loan(db.Model):
    __tablename__ = 'loans'

    loan_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    copy_id = db.Column(db.String(30), db.ForeignKey('book_copies.copy_id'), nullable=False)
    user_id = db.Column(db.String(4), db.ForeignKey('users.user_id'), nullable=False)
    checkout_date = db.Column(db.DateTime, default=utc_now, nullable=False)
    due_date = db.Column(db.DateTime, nullable=False)
    returned_date = db.Column(db.DateTime, nullable=True)
    return_condition = db.Column(db.String(20), nullable=True)
    status = db.Column(db.String(20), default='active', nullable=False)  # active, returned, lost

    copy = db.relationship('BookCopy', back_populates='loans')
    user = db.relationship('User', back_populates='loans')

    @property
    def is_overdue(self):
        if self.status == 'active' and self.due_date:
            now = utc_now()
            # Handle naive vs aware comparison safely
            due = self.due_date.replace(tzinfo=timezone.utc) if self.due_date.tzinfo is None else self.due_date
            return now > due
        return False

class Hold(db.Model):
    __tablename__ = 'holds'

    hold_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    isbn = db.Column(db.String(20), db.ForeignKey('titles.isbn'), nullable=False)
    user_id = db.Column(db.String(4), db.ForeignKey('users.user_id'), nullable=False)
    placed_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    status = db.Column(db.String(20), default='waiting', nullable=False)  # waiting, ready, fulfilled, cancelled

    title = db.relationship('Title', back_populates='holds')
    user = db.relationship('User', back_populates='holds')

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    log_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    copy_id = db.Column(db.String(30), nullable=True)
    isbn = db.Column(db.String(20), nullable=True)
    user_id = db.Column(db.String(4), nullable=True)
    action = db.Column(db.String(50), nullable=False)  # REGISTER, CHECKOUT, CHECKIN, RECONCILE, STATUS_CHANGE, CONDITION_CHANGE, DEACTIVATE
    previous_state = db.Column(db.Text, nullable=True)
    new_state = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=utc_now, nullable=False)
