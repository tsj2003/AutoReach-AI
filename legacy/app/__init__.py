"""
AutoReach - Professional Email Campaign Manager
Flask application factory
"""

from flask import Flask
from pathlib import Path
import os
import logging

from app.models import db

logger = logging.getLogger(__name__)


def create_app():
    """Application factory"""
    # Load .env in development
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    app = Flask(__name__,
                template_folder='templates',
                static_folder='static')

    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(24))
    app.config['PROJECT_ROOT'] = Path(__file__).parent.parent

    # Database config — support PostgreSQL and SQLite
    db_url = os.getenv('DATABASE_URL')
    if db_url:
        # Render and Heroku use postgres:// but SQLAlchemy 2.x requires postgresql://
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
    else:
        db_path = app.config['PROJECT_ROOT'] / 'autoreach_saas.db'
        db_url = f'sqlite:///{db_path}'

    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Connection pooling for PostgreSQL
    if db_url.startswith('postgresql://'):
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_size': 5,
            'pool_recycle': 300,
            'pool_pre_ping': True,
            'max_overflow': 10,
        }

    # Initialize Sentry error monitoring
    sentry_dsn = os.getenv('SENTRY_DSN')
    if sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.flask import FlaskIntegration
            from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

            integrations = [FlaskIntegration(), SqlalchemyIntegration()]

            # Add Celery integration if available
            try:
                from sentry_sdk.integrations.celery import CeleryIntegration
                integrations.append(CeleryIntegration())
            except ImportError:
                pass

            sentry_sdk.init(
                dsn=sentry_dsn,
                integrations=integrations,
                traces_sample_rate=0.1,
                profiles_sample_rate=0.1,
                environment=os.getenv('FLASK_ENV', 'production'),
                send_default_pii=False,
            )
            logger.info("Sentry error monitoring initialized")
        except ImportError:
            logger.warning("sentry-sdk not installed, skipping Sentry initialization")

    # Initialize DB
    db.init_app(app)

    # Register blueprints
    from app.routes import main_bp, api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    # Create DB tables
    with app.app_context():
        db.create_all()

    return app
