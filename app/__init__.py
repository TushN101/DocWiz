"""DocWiz application factory."""
import logging
from pathlib import Path

from flask import Flask, render_template

from config import Config as DefaultConfig

from .utils.errors import register_error_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

# templates/ and static/ live at the project root, one level above this package.
_BASE_DIR = Path(__file__).resolve().parent.parent


def create_app(config_object=DefaultConfig, override_settings=None):
    app = Flask(
        __name__,
        template_folder=str(_BASE_DIR / "templates"),
        static_folder=str(_BASE_DIR / "static"),
    )
    app.config.from_object(config_object)
    if override_settings:
        app.config.update(override_settings)

    # Fail fast on embedding misconfiguration (pure checks — no network).
    from .services.embedding_service import validate_embedding_config
    from app.utils.errors import AppError

    try:
        validate_embedding_config(app.config)
    except AppError as exc:
        app.logger.error("Embedding configuration error: %s", exc.message)
        raise

    from config import ensure_storage

    ensure_storage()

    register_error_handlers(app)

    from .routes.api import api_bp

    app.register_blueprint(api_bp)

    from .routes.views import views_bp

    app.register_blueprint(views_bp)

    # Long-lived singletons (embedding model loads lazily on first use).
    from .services.container import ServiceContainer

    app.extensions["docwiz"] = ServiceContainer(app.config)

    @app.teardown_appcontext
    def _nothing(_exc):  # placeholder for future per-request cleanup
        return None

    return app
