from flask import Flask

from config import Config
from .models import init_engine, init_db, remove_session
from .routes import ui_bp
from .api import api_bp
from .limiter import limiter


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize database engine and create tables
    init_engine(app.config["DATABASE_URL"])
    if app.config.get("AUTO_CREATE_DB"):
        # For development only; in production use Alembic migrations
        init_db()

    # Initialize rate limiter
    limiter.init_app(app)

    # Blueprints
    app.register_blueprint(ui_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    # Ensure sessions are cleaned up per request/app context
    @app.teardown_appcontext
    def _cleanup(exception=None):  # noqa: ARG001 - Flask teardown signature
        remove_session()

    return app
