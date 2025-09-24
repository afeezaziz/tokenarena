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
    SESSION_COOKIE_SECURE = not DEBUG
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
