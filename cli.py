import csv
import sys
import click
from pathlib import Path
from flask.cli import FlaskGroup
from app import create_app
from app.db import db
from app.models import User, Title, BookCopy, utc_now
from app.services.audit_service import record_audit

def create_cli_app():
    return create_app()

@click.group(cls=FlaskGroup, create_app=create_cli_app)
def cli():
    """Tanager Library Management System CLI."""
    pass

@cli.command("init-db")
def init_db():
    """Initialize the SQLite database schema."""
    db.create_all()
    click.echo(click.style("Database initialized successfully.", fg="green"))

@cli.command("import-users")
@click.argument("csv_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--skip-header/--no-skip-header", default=True, help="Skip the first line if it is a header.")
def import_users(csv_file, skip_header):
    """
    Bulk import users from a CSV file.
    Expected CSV columns: name, id, email, notes
    Example:
      Jane Doe,1001,jane@example.com,Staff member
      John Smith,1002,,Club volunteer
    """
    path = Path(csv_file)
    created_count = 0
    updated_count = 0
    error_count = 0

    with open(path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        row_idx = 0
        for row in reader:
            row_idx += 1
            if not row or not any(field.strip() for field in row):
                continue

            if skip_header and row_idx == 1:
                # Check if this row looks like a header
                first_col = row[0].strip().lower()
                second_col = row[1].strip().lower() if len(row) > 1 else ""
                if "name" in first_col or "id" in second_col:
                    continue

            if len(row) < 2:
                click.echo(click.style(f"Row {row_idx}: Skipped - insufficient columns (expected at least name, id)", fg="yellow"))
                error_count += 1
                continue

            name = row[0].strip()
            user_id = row[1].strip()
            email = row[2].strip() if len(row) > 2 and row[2].strip() else None
            notes = row[3].strip() if len(row) > 3 and row[3].strip() else None

            # Validate 4 digits
            if not (user_id.isdigit() and len(user_id) == 4):
                click.echo(click.style(f"Row {row_idx}: Skipped - ID '{user_id}' must be exactly 4 numeric digits.", fg="red"))
                error_count += 1
                continue

            user = User.query.filter_by(user_id=user_id).first()
            if user:
                user.name = name
                if email:
                    user.email = email
                if notes:
                    user.notes = notes
                updated_count += 1
            else:
                user = User(
                    user_id=user_id,
                    name=name,
                    email=email,
                    notes=notes,
                    is_admin=False,
                    is_active=True
                )
                db.session.add(user)
                created_count += 1

        db.session.commit()

    click.echo(click.style(
        f"Import complete: {created_count} users created, {updated_count} updated, {error_count} skipped/failed.",
        fg="green"
    ))

@cli.command("create-user")
@click.option("--id", "user_id", required=True, help="4-digit numeric User ID (e.g. 1001)")
@click.option("--name", required=True, help="Full name of user")
@click.option("--email", default=None, help="Email address (optional)")
@click.option("--notes", default=None, help="Administrative notes (optional)")
@click.option("--admin", is_flag=True, default=False, help="Grant administrator privileges")
def create_user(user_id, name, email, notes, admin):
    """Create a single user via CLI."""
    user_id = user_id.strip()
    if not (user_id.isdigit() and len(user_id) == 4):
        click.echo(click.style(f"Error: User ID '{user_id}' must be exactly 4 digits.", fg="red"))
        sys.exit(1)

    existing = User.query.filter_by(user_id=user_id).first()
    if existing:
        click.echo(click.style(f"Error: User {user_id} already exists.", fg="red"))
        sys.exit(1)

    user = User(
        user_id=user_id,
        name=name.strip(),
        email=email.strip() if email else None,
        notes=notes.strip() if notes else None,
        is_admin=admin,
        is_active=True
    )
    db.session.add(user)
    db.session.commit()
    role_str = " (Admin)" if admin else ""
    click.echo(click.style(f"User {user_id}: {name}{role_str} created successfully.", fg="green"))

@cli.command("seed-sample")
def seed_sample():
    """Populate sample users and books for testing and demonstration."""
    db.create_all()

    # Seed Admin and Members
    users_data = [
        ("0001", "Admin Staff", "admin@library.local", True, "System Administrator"),
        ("1001", "Alice Reader", "alice@example.com", False, "Avid sci-fi reader"),
        ("1002", "Bob Student", "bob@example.com", False, "University student"),
        ("1003", "Carol Volunteer", "carol@example.com", True, "Weekend volunteer librarian")
    ]
    for uid, name, email, is_admin, notes in users_data:
        if not User.query.filter_by(user_id=uid).first():
            db.session.add(User(
                user_id=uid,
                name=name,
                email=email,
                is_admin=is_admin,
                notes=notes,
                is_active=True
            ))

    # Seed Sample Books
    sample_books = [
        {
            "isbn": "9780132350884",
            "title": "Clean Code: A Handbook of Agile Software Craftsmanship",
            "authors": "Robert C. Martin",
            "description": "Even bad code can function. But if code isn't clean, it can bring a development organization to its knees.",
            "publisher": "Prentice Hall",
            "publish_year": "2008",
            "copies": 2
        },
        {
            "isbn": "9780201616224",
            "title": "The Pragmatic Programmer",
            "authors": "Andrew Hunt, David Thomas",
            "description": "One of the most significant books in software engineering, offering practical tips and timeless advice.",
            "publisher": "Addison-Wesley",
            "publish_year": "1999",
            "copies": 1
        },
        {
            "isbn": "9780134494166",
            "title": "Clean Architecture: A Craftsman's Guide to Software Structure and Design",
            "authors": "Robert C. Martin",
            "description": "Building upon the success of Clean Code, Martin gives developers essential rules of software architecture.",
            "publisher": "Prentice Hall",
            "publish_year": "2017",
            "copies": 2
        }
    ]

    for b in sample_books:
        title = Title.query.filter_by(isbn=b["isbn"]).first()
        if not title:
            title = Title(
                isbn=b["isbn"],
                title=b["title"],
                authors=b["authors"],
                description=b["description"],
                publisher=b["publisher"],
                publish_year=b["publish_year"],
                cover_image_path=None
            )
            db.session.add(title)
            db.session.flush()

            for i in range(1, b["copies"] + 1):
                copy = BookCopy(
                    copy_id=f"{b['isbn']}-{i}",
                    isbn=b["isbn"],
                    copy_number=i,
                    condition="new" if i == 1 else "good",
                    status="available",
                    location=f"Room 101 / Shelf {chr(64 + i)}",
                    registered_by="0001",
                    notes="Initial library inventory"
                )
                db.session.add(copy)
                record_audit(
                    action="REGISTER",
                    copy_id=copy.copy_id,
                    isbn=title.isbn,
                    user_id="0001",
                    new_state=f"status=available, condition={copy.condition}",
                    notes="Sample library seeding"
                )

    db.session.commit()
    click.echo(click.style("Sample database successfully seeded with users and books.", fg="green"))

if __name__ == "__main__":
    cli()
