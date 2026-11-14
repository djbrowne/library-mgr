import os
from flask import Flask, session
from app.config import Config
from app.db import db, migrate
from app.models import User

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Ensure static cover art directory exists
    covers_dir = app.config.get('COVERS_DIR')
    if covers_dir:
        covers_dir.mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)

    # Register blueprints
    from app.routes.main import bp as main_bp
    from app.routes.circulation import bp as circulation_bp
    from app.routes.catalog import bp as catalog_bp
    from app.routes.admin import bp as admin_bp
    from app.routes.reports import bp as reports_bp
    from app.routes.scanner import bp as scanner_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(circulation_bp, url_prefix='/circulation')
    app.register_blueprint(catalog_bp, url_prefix='/catalog')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(scanner_bp)

    @app.context_processor
    def inject_auth_user():
        user_id = session.get('user_id')
        current_user = None
        if user_id:
            current_user = User.query.filter_by(user_id=user_id).first()
        return dict(current_user=current_user)

    return app
