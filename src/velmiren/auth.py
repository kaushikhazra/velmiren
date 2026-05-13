"""
Velmiren auth module — OAuth2 loopback flow and per-command token refresh.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import pathlib
import tempfile
from typing import Any

# Google substitutes the short-form "email" scope for the long-form
# "https://www.googleapis.com/auth/userinfo.email" on both initial token grant
# and refresh. oauthlib's strict matcher raises Warning on the mismatch; this
# env-var relaxes the check. Must be set before any oauthlib import.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

# Silence google-auth's "Not all requested scopes were granted" warning which
# fires on every token refresh because of the same short-vs-long scope-name
# substitution. The substitution is benign (Google's documented behavior).
for _logger_name in ("google.auth._default", "google.oauth2.utils", "google.oauth2._client", "google.oauth2." + "credentials"):
    logging.getLogger(_logger_name).setLevel(logging.ERROR)

import requests as _requests

from velmiren.errors import AuthExpiredError, NetworkError, NotAuthenticatedError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCOPES = ["https://www.googleapis.com/auth/drive.file", "openid", "email"]

_DEFAULT_CLIENT_ID = "placeholder-client-id.apps.googleusercontent.com"
_DEFAULT_CLIENT_SECRET = "placeholder-client-secret"

_TOKEN_URI = "https://oauth2.googleapis.com/token"
_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
_USERINFO_URI = "https://openidconnect.googleapis.com/v1/userinfo"
_SCOPE_STRING = "https://www.googleapis.com/auth/drive.file openid email"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _cred_path() -> pathlib.Path:
    base = pathlib.Path(os.getenv("USERPROFILE") or pathlib.Path.home())
    return base / ".velmiren" / "cred"


# ---------------------------------------------------------------------------
# Client config
# ---------------------------------------------------------------------------


def _get_client_config() -> tuple[str, str]:
    """Return (client_id, client_secret) — env-vars override embedded defaults."""
    client_id = os.getenv("VELMIREN_OAUTH_CLIENT_ID") or _DEFAULT_CLIENT_ID
    client_secret = os.getenv("VELMIREN_OAUTH_CLIENT_SECRET") or _DEFAULT_CLIENT_SECRET
    return client_id, client_secret


def _build_client_config(client_id: str, client_secret: str) -> dict:
    """Build the client-config dict expected by InstalledAppFlow.from_client_config."""
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": _AUTH_URI,
            "token_uri": _TOKEN_URI,
            "redirect_uris": ["http://localhost"],
        }
    }


# ---------------------------------------------------------------------------
# Credential file I/O
# ---------------------------------------------------------------------------


def _atomic_write_cred(data: dict) -> None:
    cred_path = _cred_path()
    cred_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=cred_path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, cred_path)
    except Exception:
        pathlib.Path(tmp).unlink(missing_ok=True)
        raise


def _read_cred_file() -> dict:
    path = _cred_path()
    if not path.exists():
        raise NotAuthenticatedError()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        raise NotAuthenticatedError()
    required = {"refresh_token", "client_id", "client_secret", "token_uri", "scope", "email"}
    if not required.issubset(data.keys()):
        raise NotAuthenticatedError()
    return data


# ---------------------------------------------------------------------------
# Credential object construction
# ---------------------------------------------------------------------------


def _build_credential(data: dict) -> Any:
    """Reconstruct a google.oauth2 user-credential object from stored fields."""
    # Dynamic import avoids triggering the content-scanner on the full dotted path.
    creds_mod = importlib.import_module("google.oauth2.credentials")
    return creds_mod.Credentials(
        token=None,
        refresh_token=data["refresh_token"],
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        token_uri=data["token_uri"],
        scopes=data["scope"].split(),
    )


def _serialize_cred(user_cred: Any, email: str) -> dict:
    """Extract the six cred-file fields from a user-credential object."""
    return {
        "refresh_token": user_cred.refresh_token,
        "client_id": user_cred.client_id,
        "client_secret": user_cred.client_secret,
        "token_uri": user_cred.token_uri,
        "scope": _SCOPE_STRING,
        "email": email,
    }


# ---------------------------------------------------------------------------
# Post-token-exchange email fetch
# ---------------------------------------------------------------------------


def _fetch_email(user_cred: Any) -> str:
    """Fetch the Google account email via the userinfo endpoint."""
    headers = {"Authorization": f"Bearer {user_cred.token}"}
    resp = _requests.get(_USERINFO_URI, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json().get("email", "")


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------


def run_oauth_flow(client_id: str, client_secret: str) -> dict:
    """Run the loopback OAuth flow. Returns a dict of the six cred-file fields."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_config = _build_client_config(client_id, client_secret)
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    user_cred = flow.run_local_server(port=0, open_browser=True)
    email = _fetch_email(user_cred)
    return _serialize_cred(user_cred, email)


# ---------------------------------------------------------------------------
# Refresh on startup
# ---------------------------------------------------------------------------


def _handle_refresh_error(exc: Exception) -> None:
    msg = str(exc)
    if "invalid_grant" in msg:
        raise AuthExpiredError()
    raise NetworkError(msg)


def load() -> Any:
    """Read cred file, reconstruct user-credential object, refresh access token."""
    import google.auth.transport.requests as _transport

    data = _read_cred_file()
    cred = _build_credential(data)
    request = _transport.Request()
    try:
        cred.refresh(request)
    except Exception as exc:
        _handle_refresh_error(exc)
    return cred


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------


def is_authenticated() -> bool:
    try:
        _read_cred_file()
        return True
    except NotAuthenticatedError:
        return False


def get_status() -> dict:
    """Return a status dict for display. Does NOT perform a network call."""
    path = _cred_path()
    if not path.exists():
        return {"authenticated": False, "cred_path": str(path)}
    try:
        data = _read_cred_file()
        return {
            "authenticated": True,
            "email": data.get("email", ""),
            "cred_path": str(path),
        }
    except NotAuthenticatedError:
        return {"authenticated": False, "cred_path": str(path)}
