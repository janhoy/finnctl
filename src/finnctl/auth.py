"""
Session management for finn.no.

Stores a raw Cookie header value captured from the browser after login.
Cookie string is saved to ~/.finnctl/session.json (mode 0600).

Library users: call load_session() to retrieve a stored session, or construct
a Session(cookie="...") directly if you have obtained cookies by other means.
"""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


SESSION_FILE = Path.home() / ".finnctl" / "session.json"

FINN_LOGIN_URL = "https://www.finn.no/auth/login"


@dataclass
class Session:
    cookie: str
    email: str | None = None
    login_id: int | None = None
    spid_id: int | None = None
    # Legacy fields kept for backwards-compat when loading old Bearer-token sessions
    access_token: str = ""
    refresh_token: str | None = None
    expires_at: float = 0.0

    @property
    def is_expired(self) -> bool:
        # Cookie sessions have no predictable expiry; treat as always valid.
        return False

    def auth_header(self) -> dict[str, str]:
        """Return a headers dict suitable for use with httpx / requests."""
        return {"Cookie": self.cookie}


def load_session() -> "Session | None":
    """Load the saved session from disk. Returns None if not found or invalid."""
    if not SESSION_FILE.exists():
        return None
    try:
        with open(SESSION_FILE) as f:
            data = json.load(f)
        if "cookie" not in data:
            # Old Bearer-token session — not usable with the current auth scheme.
            return None
        known = {k: v for k, v in data.items() if k in Session.__dataclass_fields__}
        return Session(**known)
    except Exception:
        return None


def save_session(session: "Session") -> None:
    """Persist session to disk with 0600 permissions."""
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SESSION_FILE, "w") as f:
        json.dump(asdict(session), f, indent=2)
    os.chmod(SESSION_FILE, 0o600)


def clear_session() -> None:
    """Delete the saved session file."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def require_session() -> "Session":
    """Return the active session or raise RuntimeError if not logged in."""
    session = load_session()
    if session is None:
        raise RuntimeError("Not logged in. Run: finnctl login")
    return session
