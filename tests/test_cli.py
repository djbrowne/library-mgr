import tempfile
from pathlib import Path
from click.testing import CliRunner
from cli import cli
from app.models import User

def test_cli_import_users(app):
    # Prepare temporary CSV
    csv_content = """name,id,email,notes
Grace Hopper,1042,grace@navy.mil,Computing Pioneer
Alan Turing,1043,alan@bletchley.uk,Mathematician
Invalid ID User,12,,Should be rejected
Katherine Johnson,1044,,NASA Mathematician
"""
    with tempfile.NamedTemporaryFile("w+", suffix=".csv", delete=False) as f:
        f.write(csv_content)
        temp_path = f.name

    runner = CliRunner()
    result = runner.invoke(cli, ["import-users", temp_path])
    assert result.exit_code == 0
    assert "3 users created" in result.output
    assert "1 skipped/failed" in result.output

    with app.app_context():
        u1 = User.query.filter_by(user_id="1042").first()
        assert u1 is not None
        assert u1.name == "Grace Hopper"
        assert u1.email == "grace@navy.mil"

        u2 = User.query.filter_by(user_id="1044").first()
        assert u2 is not None
        assert u2.name == "Katherine Johnson"
        assert u2.email is None

        # Verify invalid 2-digit ID was rejected
        bad_u = User.query.filter_by(user_id="12").first()
        assert bad_u is None

    Path(temp_path).unlink(missing_ok=True)

def test_cli_create_single_user(app):
    runner = CliRunner()
    res = runner.invoke(cli, ["create-user", "--id", "2001", "--name", "Ada Lovelace", "--email", "ada@example.com", "--admin"])
    assert res.exit_code == 0
    assert "created successfully" in res.output

    with app.app_context():
        u = User.query.filter_by(user_id="2001").first()
        assert u is not None
        assert u.name == "Ada Lovelace"
        assert u.is_admin is True
