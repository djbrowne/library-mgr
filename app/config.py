import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'tanager-library-secret-key-change-in-prod')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', f'sqlite:///{BASE_DIR / "library.db"}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DEFAULT_LOAN_DAYS = 60
    COVERS_DIR = BASE_DIR / 'app' / 'static' / 'covers'

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
