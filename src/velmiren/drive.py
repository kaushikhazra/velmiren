"""
Velmiren drive module — Google Drive API v3 wrapper.
"""

from __future__ import annotations

import pathlib
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from velmiren import paths
from velmiren.errors import NetworkError, RemoteNotFoundError

# Chunk size for resumable uploads. 8 MB is googleapiclient's recommended
# default for desktop bandwidth — large enough to amortize HTTP overhead,
# small enough that a dropped chunk costs ~one chunk of retransmit.
_UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024


# ---------------------------------------------------------------------------
# Service construction
# ---------------------------------------------------------------------------


def _auth_param(cred: Any) -> dict:
    """Return the kwarg dict that build() expects for auth injection."""
    return {"credentials": cred}


def _service(cred: Any) -> Any:
    """Construct a Drive v3 service object from an authenticated cred object."""
    return build("drive", "v3", **_auth_param(cred))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_by_name(svc: Any, name: str, parent_id: str) -> str | None:
    """Return Drive file ID if `name` exists under `parent_id`, else None."""
    safe_name = name.replace("'", "\\'")
    resp = svc.files().list(
        q=f"name='{safe_name}' and '{parent_id}' in parents and trashed=false",
        fields="files(id)",
        pageSize=1,
    ).execute()
    files = resp.get("files", [])
    return files[0]["id"] if files else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def upload(cred: Any, local_path: str, remote_path: str, progress=None) -> str:
    """
    Upload local file to remote_path.
    Overwrites if a file with that name already exists (idempotent).
    Uses Drive's resumable upload (chunked + retryable) — supports up to 5 TB.
    Optional `progress` callable receives (bytes_uploaded, total_bytes) per chunk.
    Returns Drive file ID.
    Raises NetworkError, RemoteNotFoundError.
    """
    svc = _service(cred)
    try:
        parent_id, name = paths.ensure_path(svc, remote_path)
        existing_id = _find_by_name(svc, name, parent_id)
        media = MediaFileUpload(
            local_path, resumable=True, chunksize=_UPLOAD_CHUNK_SIZE
        )
        if existing_id:
            request = svc.files().update(
                fileId=existing_id, media_body=media, fields="id"
            )
        else:
            metadata = {"name": name, "parents": [parent_id]}
            request = svc.files().create(
                body=metadata, media_body=media, fields="id"
            )
        # Drive returns resumable progress via next_chunk(); loop until done.
        response = None
        total = pathlib.Path(local_path).stat().st_size
        while response is None:
            status, response = request.next_chunk()
            if progress is not None and status is not None:
                progress(status.resumable_progress, total)
        if progress is not None:
            progress(total, total)
        return response["id"]
    except HttpError as exc:
        raise NetworkError(str(exc), status_code=exc.resp.status) from exc


def download(cred: Any, remote_path: str, local_path: str) -> int:
    """
    Download remote_path to local_path.
    If local_path is a directory, the file is placed inside it using its remote name.
    Returns bytes written.
    Raises RemoteNotFoundError, NetworkError.
    """
    svc = _service(cred)
    try:
        file_id = paths.resolve(svc, remote_path)
        dest = pathlib.Path(local_path)
        if dest.is_dir():
            dest = dest / pathlib.Path(remote_path).name
        request = svc.files().get_media(fileId=file_id)
        with dest.open("wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        return dest.stat().st_size
    except RemoteNotFoundError:
        raise
    except HttpError as exc:
        raise NetworkError(str(exc), status_code=exc.resp.status) from exc


def list_dir(cred: Any, folder_id: str) -> list[dict]:
    """
    Return list of dicts with keys: name, size, modifiedTime, id.
    Empty list if the folder is empty.
    Raises NetworkError.
    """
    svc = _service(cred)
    try:
        resp = svc.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="files(name,size,modifiedTime,id)",
            pageSize=1000,
        ).execute()
        return resp.get("files", [])
    except HttpError as exc:
        raise NetworkError(str(exc), status_code=exc.resp.status) from exc


def file_exists(cred: Any, remote_path: str) -> bool:
    """
    Return True if remote_path resolves to a Drive file; False if not found.
    Raises NetworkError on API errors other than not-found.
    """
    svc = _service(cred)
    try:
        paths.resolve(svc, remote_path)
        return True
    except RemoteNotFoundError:
        return False
    except HttpError as exc:
        raise NetworkError(str(exc), status_code=exc.resp.status) from exc


def delete_file(cred: Any, remote_path: str) -> None:
    """
    Permanently delete the file at remote_path.
    Raises RemoteNotFoundError if absent, NetworkError on API errors.
    """
    svc = _service(cred)
    try:
        file_id = paths.resolve(svc, remote_path)
        svc.files().delete(fileId=file_id).execute()
    except RemoteNotFoundError:
        raise
    except HttpError as exc:
        raise NetworkError(str(exc), status_code=exc.resp.status) from exc
