import os
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///token_battles.db")
    DEBUG = os.getenv("DEBUG", "0") == "1"
    # Session cookie security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Secure cookies off for local dev over http (e.g., localhost) or when DEBUG=1
    # This prevents dropped cookies on http during development.
    SESSION_COOKIE_SECURE = not (
        DEBUG or os.getenv("SITE_URL", "http://localhost:5000").startswith("http://")
    )
    PERMANENT_SESSION_LIFETIME = timedelta(seconds=int(os.getenv("SESSION_LIFETIME_SECONDS", "2592000")))  # 30 days default
    # Upload limits
    AVATAR_MAX_BYTES = int(os.getenv("AVATAR_MAX_BYTES", str(2 * 1024 * 1024)))  # 2MB default
    MAX_CONTENT_LENGTH = AVATAR_MAX_BYTES
    # Optional S3 for avatars (presigned uploads)
    S3_AVATAR_BUCKET = os.getenv("S3_AVATAR_BUCKET")
    S3_REGION = os.getenv("S3_REGION")
    S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID")
    S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY")
    S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")  # optional (e.g., MinIO / Cloudflare R2)
    S3_PUBLIC_BASE_URL = os.getenv("S3_PUBLIC_BASE_URL")  # optional public base URL override
    # Optional: auto-create tables at startup (dev only). With Alembic, keep disabled.
    AUTO_CREATE_DB = os.getenv("AUTO_CREATE_DB", "0") == "1"

    # Site / SEO
    SITE_NAME = os.getenv("SITE_NAME", "Token Arena")
    SITE_URL = os.getenv("SITE_URL", "http://localhost:5000")  # used for canonical/og:url
    DEFAULT_DESCRIPTION = os.getenv(
        "DEFAULT_DESCRIPTION",
        "Battle-ready market intel: leaderboards, holders, charts and competitions.",
    )
    DEFAULT_SOCIAL_IMAGE = os.getenv(
        "DEFAULT_SOCIAL_IMAGE",
        # Fallback to favicon or a static placeholder; update to a proper OG image when available
        "/static/favicon.svg",
    )
    STATIC_VERSION = os.getenv("STATIC_VERSION", "1")
    STATIC_CACHE_SECONDS = int(os.getenv("STATIC_CACHE_SECONDS", "86400"))

    # Analytics
    ANALYTICS_PLAUSIBLE_DOMAIN = os.getenv("ANALYTICS_PLAUSIBLE_DOMAIN")  # e.g., tokenarena.example
    ANALYTICS_GA4_ID = os.getenv("ANALYTICS_GA4_ID")  # e.g., G-XXXXXXXXXX
    # Social
    TWITTER_SITE = os.getenv("TWITTER_SITE")  # e.g., @tokenarena

    # Dev toggles
    NOSTR_VERIFY_DISABLED = os.getenv("NOSTR_VERIFY_DISABLED", "0") == "1"
