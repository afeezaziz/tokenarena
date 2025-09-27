from flask import Flask
from flask import render_template, request
try:
    from flask_compress import Compress  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Compress = None
from datetime import timedelta
from whitenoise import WhiteNoise

from config import Config
from .models import init_engine, init_db, remove_session
from .routes import ui_bp
from .api import api_bp
from .limiter import limiter as rate_limiter

def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    # Static file cache max age
    try:
        app.config['SEND_FILE_MAX_AGE_DEFAULT'] = timedelta(seconds=int(app.config.get('STATIC_CACHE_SECONDS', 86400)))
    except Exception:
        pass

    # Initialize database engine and create tables
    init_engine(app.config["DATABASE_URL"])
    if app.config.get("AUTO_CREATE_DB"):
        # For development only; in production use Alembic migrations
        init_db()

    # Initialize rate limiter
    rate_limiter.init_app(app)

    # Enable compression if available
    if Compress is not None:
        try:
            Compress(app)
        except Exception:
            pass

    # Static files via WhiteNoise for efficient static serving
    try:
        static_prefix = app.static_url_path or '/static'
        if not static_prefix.endswith('/'):
            static_prefix = static_prefix + '/'
        max_age = int(app.config.get('STATIC_CACHE_SECONDS', 86400))
    except Exception:
        static_prefix = '/static/'
        max_age = 86400
    app.wsgi_app = WhiteNoise(
        app.wsgi_app,
        root=app.static_folder,
        prefix=static_prefix,
        max_age=max_age,
        autorefresh=app.debug,
    )

    # Blueprints
    app.register_blueprint(ui_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    # Simple healthcheck endpoint
    @app.get('/healthz')
    def healthz():  # noqa: D401
        return {'status': 'ok'}, 200

    # Ensure sessions are cleaned up per request/app context
    @app.teardown_appcontext
    def _cleanup(exception=None):  # noqa: ARG001 - Flask teardown signature
        remove_session()

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):  # noqa: ANN001 - Flask handler signature
        return render_template('404.html'), 404

    # Context: site meta and analytics
    @app.context_processor
    def inject_site_meta():  # noqa: D401
        cfg = app.config
        site_url = cfg.get('SITE_URL', '').rstrip('/') or request.host_url.rstrip('/')
        path = request.path
        canonical_url = f"{site_url}{path}"
        social_image = cfg.get('DEFAULT_SOCIAL_IMAGE') or ''
        if social_image and social_image.startswith('/'):
            social_image_url = f"{site_url}{social_image}"
        else:
            social_image_url = social_image
        # Robots
        is_local = ('localhost' in site_url) or ('127.0.0.1' in site_url)
        robots = 'noindex,nofollow' if (app.debug or is_local) else 'index,follow'
        def abs_url(p: str) -> str:
            if not p:
                return ''
            if p.startswith('http://') or p.startswith('https://'):
                return p
            if not p.startswith('/'):
                p = '/' + p
            return f"{site_url}{p}"
        return dict(
            SITE_NAME=cfg.get('SITE_NAME', 'Token Arena'),
            SITE_URL=site_url,
            DEFAULT_DESCRIPTION=cfg.get('DEFAULT_DESCRIPTION', ''),
            DEFAULT_SOCIAL_IMAGE=social_image_url,
            STATIC_VERSION=cfg.get('STATIC_VERSION', '1'),
            ANALYTICS_PLAUSIBLE_DOMAIN=cfg.get('ANALYTICS_PLAUSIBLE_DOMAIN'),
            ANALYTICS_GA4_ID=cfg.get('ANALYTICS_GA4_ID'),
            canonical_url=canonical_url,
            ROBOTS_DIRECTIVE=robots,
            abs_url=abs_url,
            TWITTER_SITE=cfg.get('TWITTER_SITE'),
        )

    # Security headers
    @app.after_request
    def set_security_headers(resp):  # noqa: D401
        # Basic hardening headers
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('X-Frame-Options', 'DENY')
        resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        resp.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')
        # HSTS only when secure
        try:
            if request.is_secure:
                resp.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains; preload')
        except Exception:
            pass
        # Content-Security-Policy (relaxed for inline scripts used by analytics)
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://plausible.io https://www.googletagmanager.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' data: blob: https://picsum.photos https://plausible.io https://www.googletagmanager.com https://dummyimage.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self' https://plausible.io https://www.googletagmanager.com; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'" 
        )
        # Do not override if user/app explicitly set one upstream
        if 'Content-Security-Policy' not in resp.headers:
            resp.headers['Content-Security-Policy'] = csp
        return resp

    return app
