"""
Velmiren paths module — remote path → Drive file-ID resolution.
"""

from __future__ import annotations

import os
from typing import Any

from velmiren.errors import RemoteNotFoundError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_ROOT_FOLDER = "velmiren"
_FOLDER_MIME = "application/vnd.google-apps.folder"

# Per-session cache: remote_path → Drive file ID
_cache: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Remote root resolution
# ---------------------------------------------------------------------------


def _resolve_remote_root() -> str:
    """
    Return the effective remote root.

    Rules:
    - If VELMIREN_REMOTE_ROOT is set and begins with ``id:``, strip the
      prefix and return the raw Drive file ID.
    - If VELMIREN_REMOTE_ROOT is set to a plain name, return that name.
    - Otherwise return the default folder name "velmiren".
    """
    raw = os.getenv("VELMIREN_REMOTE_ROOT", "")
    if raw.startswith("id:"):
        return raw[3:]  # raw Drive file ID — used directly as parent_id
    return raw or _DEFAULT_ROOT_FOLDER


def resolve_root_id(svc: Any) -> str:
    """
    Return the Drive file ID of the configured remote root folder.

    Reads ``VELMIREN_REMOTE_ROOT`` via ``_resolve_remote_root()``:
    - If the env var used the ``id:`` prefix the stripped ID is returned directly.
    - Otherwise the root folder name is looked up under Drive's ``root`` alias.

    Raises RemoteNotFoundError if the root folder is not found.
    """
    root = _resolve_remote_root()
    env_raw = os.getenv("VELMIREN_REMOTE_ROOT", "")
    if env_raw.startswith("id:"):
        return root  # already a bare Drive file ID
    found = _lookup_child(svc, root, "root", folder_only=True)
    if not found:
        raise RemoteNotFoundError("no such remote folder")
    return found


def _is_drive_id(value: str) -> bool:
    """Return True if value looks like a bare Drive file ID (returned from _resolve_remote_root)."""
    # IDs have been stripped of the "id:" prefix already; a folder name won't
    # contain slashes or spaces and will typically be short, but we distinguish
    # by checking whether the env var had the "id:" prefix (handled in _resolve_remote_root).
    # After stripping the prefix, the caller knows it's an ID; this helper is
    # unused at call sites — logic is embedded inline. Kept for testability.
    return len(value) >= 25 and value.isalnum()


# ---------------------------------------------------------------------------
# Low-level folder lookup / creation
# ---------------------------------------------------------------------------


def _lookup_child(svc: Any, name: str, parent_id: str, folder_only: bool) -> str | None:
    """Return the Drive ID of the first child named `name` under `parent_id`."""
    safe_name = name.replace("'", "\\'")
    q = f"name='{safe_name}' and '{parent_id}' in parents and trashed=false"
    if folder_only:
        q += f" and mimeType='{_FOLDER_MIME}'"
    resp = svc.files().list(q=q, fields="files(id)", pageSize=1).execute()
    files = resp.get("files", [])
    return files[0]["id"] if files else None


def _get_or_create_folder(svc: Any, name: str, parent_id: str) -> str:
    """Return the Drive ID for folder `name` under `parent_id`, creating it if absent."""
    existing = _lookup_child(svc, name, parent_id, folder_only=True)
    if existing:
        return existing
    result = svc.files().create(
        body={
            "name": name,
            "mimeType": _FOLDER_MIME,
            "parents": [parent_id],
        },
        fields="id",
    ).execute()
    return result["id"]


# ---------------------------------------------------------------------------
# Walk algorithm
# ---------------------------------------------------------------------------


def _walk(svc: Any, remote_path: str) -> str:
    """
    Walk `remote_path` and return the Drive file ID of the leaf.
    Raises RemoteNotFoundError if any segment is missing.
    """
    root = _resolve_remote_root()
    segments = remote_path.strip("/").split("/")

    # Determine starting parent_id.
    # If root is a bare Drive ID (env var used id: prefix), use it directly.
    # Otherwise treat root as a folder name under Drive's "root" alias.
    env_raw = os.getenv("VELMIREN_REMOTE_ROOT", "")
    if env_raw.startswith("id:"):
        parent_id = root  # already stripped to bare ID
    else:
        # Walk starts by looking up the root folder name under My Drive root,
        # then continues with the path segments.
        parent_id = "root"
        # Prepend the root folder name as first segment if not already present
        if segments[0] != root:
            segments = [root] + segments

    # Walk all segments except the last as folders
    for seg in segments[:-1]:
        found = _lookup_child(svc, seg, parent_id, folder_only=True)
        if not found:
            raise RemoteNotFoundError(f"no such remote folder: {seg}")
        parent_id = found

    # Look up the last segment (file or folder)
    found = _lookup_child(svc, segments[-1], parent_id, folder_only=False)
    if not found:
        raise RemoteNotFoundError(f"no such remote file: {segments[-1]}")
    return found


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve(svc: Any, remote_path: str) -> str:
    """Return Drive file ID for remote_path. Raises RemoteNotFoundError if not found."""
    if remote_path in _cache:
        return _cache[remote_path]
    file_id = _walk(svc, remote_path)
    _cache[remote_path] = file_id
    return file_id


def ensure_path(svc: Any, remote_path: str) -> tuple[str, str]:
    """
    Walk remote_path, creating missing intermediate folders.
    Return (parent_folder_id, leaf_name).
    """
    root = _resolve_remote_root()
    env_raw = os.getenv("VELMIREN_REMOTE_ROOT", "")

    segments = remote_path.strip("/").split("/")

    if env_raw.startswith("id:"):
        parent_id = root
    else:
        parent_id = "root"
        if segments[0] != root:
            segments = [root] + segments

    for seg in segments[:-1]:
        parent_id = _get_or_create_folder(svc, seg, parent_id)

    return parent_id, segments[-1]
