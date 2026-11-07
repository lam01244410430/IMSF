"""Explicit browser origin policy. Bearer routes never authenticate cookies."""
import os
from urllib.parse import urlsplit
from fastapi import HTTPException


def allowed_origins():
    origins = [value.strip() for value in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if value.strip()]
    for value in origins:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.netloc
                or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment
                or "*" in value):
            raise RuntimeError("CORS_ALLOWED_ORIGINS must contain explicit origins only")
    return origins


def require_refresh_origin(request):
    origin = request.headers.get("origin")
    if origin is None:
        referer = request.headers.get("referer", "")
        try:
            parsed = urlsplit(referer)
            origin = f"{parsed.scheme}://{parsed.netloc}" if not parsed.username and not parsed.password else None
        except ValueError:
            origin = None
    if origin not in allowed_origins():
        raise HTTPException(status_code=403)
