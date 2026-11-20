"""Read application settings once for the legacy StudyMate service."""

from __future__ import annotations

import os
import secrets

GEMINI_API_KEY: str | None = os.environ.get("GEMINI_API_KEY")
SECRET_KEY: str | None = os.environ.get("SECRET_KEY")


def create_secret_key() -> str:
    """Return the configured Flask secret or a process-local development key.

    Returns:
        The configured secret when present, otherwise a random key for this
        process. Set ``SECRET_KEY`` to keep authentication tokens valid after
        an application restart.
    """
    return SECRET_KEY or secrets.token_urlsafe(32)
