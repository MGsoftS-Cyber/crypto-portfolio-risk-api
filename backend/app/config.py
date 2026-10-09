"""Environment configuration. Local development deliberately needs no cloud service."""

import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./crypto.db")
ALLOWED_ORIGINS = {
    value.strip()
    for value in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:8088,http://127.0.0.1:8088,http://localhost:8008,http://127.0.0.1:8008",
    ).split(",")
    if value.strip()
}
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
SESSION_SECONDS = 60 * 60 * 24 * 7
