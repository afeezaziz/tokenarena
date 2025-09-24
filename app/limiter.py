from __future__ import annotations

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os

# Memory storage is fine for dev. For prod, configure Redis or another backend:
# storage_uri="redis://localhost:6379"
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120 per minute"],
    storage_uri=os.getenv("LIMITER_STORAGE_URI", "memory://"),
)
