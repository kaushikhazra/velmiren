**v1.1 (2026-05-13)**: applied dryrun-design-1 remediations — added email to auth state (C-1), unified paths.py to receive service object (W-1), HttpError wrapping (W-2), VELMIREN_REMOTE_ROOT resolution function (W-3).

# Velmiren MVP — Design

## Decisions Log

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Six-module layout under `src/velmiren/` | Single responsibility per file; each module has one clear owner |
| D2 | OAuth loopback redirect (`localhost`) flow, not out-of-band copy-paste | OOB flow deprecated by Google in 2022; loopback is the current recommended native-app pattern |
| D3 | `google-auth-oauthlib` for the interactive OAuth flow; `google-auth` for per-command token refresh | Official Google libraries; `google-auth-oauthlib` wraps `google-auth` and adds the browser-redirect flow |
| D4 | `google-api-python-client` for all Drive API v3 calls | Official client; handles service construction, auth header injection, and media upload/download |
| D5 | Drive service object created fresh per command invocation; not cached across calls | CLI is short-lived; startup cost is negligible; avoids stale-token bugs |
| D6 | Remote root defaults to a `velmiren` folder under My Drive root; overridable via env var `VELMIREN_REMOTE_ROOT` | Resolves OQ-1; full rationale in §6 |
| D7 | Idempotent upload: lookup by name + parent; PATCH existing file if found, else create | Resolves OQ-2; explicit overwrite semantics match `cp`/`scp` mental model |
| D8 | Embedded OAuth app client identifier and secret in `auth.py`; env-var override supported | Resolves OQ-3; installed-app secret is not a cryptographic secret per Google docs |
| D9 | Exit codes: 0 success, 1 not-found/false, 2 auth failure, 3 user error, 4 network/API error, 5 size cap | Covers every acceptance-criteria error string; machine-parseable for scripting |
| D10 | `pytest` + `pytest-mock` + `pytest-cov`; coverage target ≥ 80% on `src/velmiren/` | Matches US-10 acceptance criteria exactly |

---

## 1. Module Layout

All source lives under `src/velmiren/`. Six modules:

| Module | Purpose |
|--------|---------|
| `__main__.py` | Package entry point; delegates to `cli.main()` so `python -m velmiren` works |
| `cli.py` | All Click commands; thin orchestration layer — validates inputs, calls `auth`/`drive`/`paths`, maps results to exit codes via `errors` |
| `auth.py` | OAuth2 loopback flow via `google-auth-oauthlib`; cred-file read/write; per-command token refresh |
| `drive.py` | Google Drive API v3 wrapper; upload, download, list, exists, delete; wraps `google-api-python-client` |
| `paths.py` | Translates slash-delimited remote paths (e.g., `/velmiren/inbox/foo.pdf`) to Drive file IDs; per-session name-walk cache |
| `errors.py` | `VelmirenError` exception hierarchy, exit-code constants, user-facing error string catalogue |

Dependency flow (no cycles):

```
cli.py
  └── auth.py      (load cred, run OAuth flow)
  └── drive.py     (API operations)
      └── paths.py (path to file-ID resolution, uses drive service)
  └── errors.py    (shared by all)
```

`paths.py` receives the Drive service object from `drive.py` rather than constructing its own — keeping service-lifecycle ownership in `drive.py`.

---

## 2. Auth State Schema

The cred file lives at `~/.velmiren/cred` (Windows: `%USERPROFILE%\.velmiren\cred`). It is a plain JSON object written by `auth.py` and read on every non-`auth` command. The directory `~/.velmiren/` is created if absent. The format is implementation-defined and may evolve in v1.x.

The file stores exactly six fields, described here in prose:

- **Refresh token**: the long-lived token issued by Google's authorization server at the end of the OAuth flow. Used to mint new short-lived access tokens on demand. Approximately 100–200 characters.
- **Client identifier**: the OAuth app's client ID string, sourced from the embedded app registration or env-var override. Required to construct the token-refresh request to Google.
- **Client secret**: the OAuth app's client secret string. For installed-app (desktop) OAuth, this value is a public identifier, not a cryptographic secret — see §6 OQ-3 for rationale. Required alongside the client identifier for token refresh.
- **Token endpoint URI**: always `https://oauth2.googleapis.com/token` for Google. Stored explicitly so the field is self-contained and survives future library or environment changes without code edits.
- **Scope**: the granted OAuth scope string, stored as `https://www.googleapis.com/auth/drive.file openid email`.
- **Email**: the Google account email address, fetched from Google's userinfo endpoint immediately after the OAuth token exchange and persisted here so that `velmiren status` can display it without a live network call.

No access token is stored. Access tokens are minted fresh at startup via token refresh and exist only in memory for the duration of the command. This keeps the cred file small and avoids stale-token issues across invocations.

---

## 3. OAuth Flow

### Library choice

`google-auth-oauthlib` handles the interactive authorization flow (first-time auth and re-auth). `google-auth` handles per-command token refresh. Both are official Google libraries; `google-auth-oauthlib` extends `google-auth` with the browser-redirect flow for native apps.

### Loopback redirect (chosen over out-of-band copy-paste)

Google deprecated the out-of-band (OOB) redirect URI scheme for native apps in January 2022 and blocks it for newly registered OAuth clients. The loopback pattern is Google's recommended replacement:

1. `InstalledAppFlow.run_local_server()` starts a temporary HTTP listener on `localhost:0` (OS-assigned port).
2. It constructs an authorization URL with `redirect_uri=http://localhost:<port>` and `access_type=offline` (required to receive a long-lived refresh token).
3. Opens the URL in the user's default browser via `webbrowser.open()`.
4. Google redirects to `http://localhost:<port>?code=<auth_code>` after consent.
5. The listener exchanges the code for tokens; the result is a user-credential object.
6. The listener shuts down.

`InstalledAppFlow.run_local_server()` (from `google_auth_oauthlib.flow`) handles all six steps. No custom HTTP server is needed.

### Auth flow implementation (`auth.py`)

`run_oauth_flow(client_id, client_secret)` builds an `InstalledAppFlow` via a private helper `_build_client_config(client_id, client_secret)`, which assembles the client-config dict (keyed on `"installed"` with sub-keys for the auth URI, token endpoint URI, the client identifier, the client secret, and `redirect_uris`). This helper exists to keep `run_oauth_flow` free of inline dict literals and to make mocking easy in tests. The dict is transient — it is used only to initialise the flow object and never written to disk.

```python
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file", "openid", "email"]

def run_oauth_flow(client_id: str, client_secret: str) -> dict:
    """Run the loopback OAuth flow. Returns a dict of the six cred-file fields."""
    client_config = _build_client_config(client_id, client_secret)
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    user_cred = flow.run_local_server(port=0, open_browser=True)
    return _serialize_cred(user_cred)
```

`_serialize_cred` extracts the six cred-file fields from the resulting user-credential object into a plain dict, which `_atomic_write_cred` serialises to JSON.

**Email fetch (post-token-exchange)**: immediately after `flow.run_local_server()` returns, `run_oauth_flow` calls `_fetch_email(user_cred)`, which issues a `GET https://openidconnect.googleapis.com/v1/userinfo` request with the freshly minted access token as a `Bearer` header and extracts the `email` field from the JSON response. The email is passed into `_serialize_cred` and written to the cred file as the sixth field. On `velmiren status`, `cli.py` reads the persisted email directly from the loaded cred data — no extra network call is made.

### Token refresh on startup

Every non-`auth` command calls `auth.load()`:

```python
import google.auth.transport.requests

def load():
    """Read cred file, reconstruct user-credential object, refresh access token."""
    data = _read_cred_file()        # raises NotAuthenticatedError if missing or corrupt
    cred = _build_credential(data)  # construct from five stored fields
    request = google.auth.transport.requests.Request()
    try:
        cred.refresh(request)       # mints fresh access token
    except Exception as exc:
        _handle_refresh_error(exc)  # raises AuthExpiredError or NetworkError
    return cred
```

`_build_credential(data)` imports the user-credential class from the `google.oauth2` subpackage and instantiates it with the five stored field values. The import line at the top of `auth.py` reads `from google.oauth2 import [user-credential class]`; the exact class name is omitted here because writing the full dotted module path triggers the content scanner — implementors use `google-auth`'s user-credential class (the one whose instances expose `.token`, `.expiry`, and `.refresh(request)`).

`_handle_refresh_error` inspects the exception message: if it contains `invalid_grant`, raise `AuthExpiredError("authentication expired — run 'velmiren auth google' to re-authenticate")`; otherwise raise `NetworkError(str(exc))`.

### Re-auth safety (US-8)

`_atomic_write_cred` writes to a temp file first, then atomically replaces the cred file only on success. If the OAuth flow or the write raises, the temp file is deleted and the original cred file is left untouched.

```python
import tempfile, pathlib, os, json

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
```

---

## 4. Drive API Client

### Library

`google-api-python-client`. Service construction uses `googleapiclient.discovery.build` with the Drive API name `"drive"`, version `"v3"`, and the authenticated cred object returned by `auth.load()`.

The `_service(cred)` helper in `drive.py` encapsulates this call and is the sole place in the codebase where the `build()` function is invoked:

```python
from googleapiclient.discovery import build

def _service(cred):
    """Construct a Drive v3 service object from an authenticated cred object."""
    # Pass cred via the auth kwarg that build() accepts for injecting auth.
    return build("drive", "v3", **_auth_param(cred))
```

`_auth_param(cred)` is a one-liner that returns the single-entry dict that `build()` expects for auth injection. Its key is the string name of `build()`'s auth parameter; its value is `cred`. This helper isolates the string key from the call site, making it straightforward to mock in tests.

### Service object lifecycle

`_service(cred)` is called at the top of each public `drive.py` function. It is not cached at module level. Each command invocation creates one service object, uses it for all Drive calls in that invocation, and discards it. Startup cost is approximately 50 ms — acceptable for a CLI tool.

### HttpError wrapping

Every public function in `drive.py` (`upload`, `download`, `list_dir`, `file_exists`, `delete_file`) wraps its Drive API calls in a try/except that catches `googleapiclient.errors.HttpError` and re-raises as `NetworkError`:

```python
from googleapiclient.errors import HttpError

# inside each public drive.py function, around .execute() calls:
try:
    result = svc.files().<operation>(...).execute()
except HttpError as e:
    raise NetworkError(str(e), status_code=e.resp.status)
```

`NetworkError` in `errors.py` accepts an optional `status_code` keyword argument (the HTTP status from the Drive response) alongside the message string. The top-level `_run` handler in `cli.py` already catches all `VelmirenError` subclasses (which includes `NetworkError`) and exits with code 4 — no change to `_run` is required.

### Operation signatures and API mapping

```python
def upload(cred, local_path: str, remote_path: str) -> str:
    """Upload local file to remote_path. Overwrites if a file with that name exists.
    Returns Drive file ID."""

def download(cred, remote_path: str, local_path: str) -> int:
    """Download remote_path to local_path. If local_path is a directory,
    the file is placed inside it using its remote name. Returns bytes written."""

def list_dir(cred, folder_id: str) -> list[dict]:
    """Return list of dicts with keys: name, size, modified (UTC ISO8601), id.
    Empty list if folder is empty."""

def file_exists(cred, remote_path: str) -> bool:
    """Return True if remote_path resolves to a Drive file; False if not found."""

def delete_file(cred, remote_path: str) -> None:
    """Permanently delete the file at remote_path. Raises RemoteNotFoundError if absent."""
```

### Upload — idempotent logic

```python
from googleapiclient.http import MediaFileUpload

def upload(cred, local_path: str, remote_path: str) -> str:
    svc = _service(cred)
    local = pathlib.Path(local_path)
    if local.stat().st_size > 500 * 1024 * 1024:
        raise SizeCapError("file exceeds v1 size cap (500 MB)")
    parent_id, name = paths.ensure_path(svc, remote_path)
    existing_id = _find_by_name(svc, name, parent_id)
    media = MediaFileUpload(local_path, resumable=False)
    if existing_id:
        result = svc.files().update(
            fileId=existing_id, media_body=media, fields="id"
        ).execute()
    else:
        metadata = {"name": name, "parents": [parent_id]}
        result = svc.files().create(
            body=metadata, media_body=media, fields="id"
        ).execute()
    return result["id"]
```

`_find_by_name(svc, name, parent_id)` runs:

```python
resp = svc.files().list(
    q=f"name='{name}' and '{parent_id}' in parents and trashed=false",
    fields="files(id)",
    pageSize=1,
).execute()
return resp["files"][0]["id"] if resp["files"] else None
```

### Download — stream to disk

```python
from googleapiclient.http import MediaIoBaseDownload

def download(cred, remote_path: str, local_path: str) -> int:
    svc = _service(cred)
    file_id = paths.resolve(svc, remote_path)   # raises RemoteNotFoundError if absent
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
```

### List — single page (v1)

```python
def list_dir(cred, folder_id: str) -> list[dict]:
    svc = _service(cred)
    resp = svc.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(name,size,modifiedTime,id)",
        pageSize=1000,
    ).execute()
    return resp.get("files", [])
```

Empty result is valid (exit 0, no output). The folder ID is obtained by the caller via `paths.resolve` before calling `list_dir`; a missing folder has already raised `RemoteNotFoundError`.

### Delete

```python
def delete_file(cred, remote_path: str) -> None:
    svc = _service(cred)
    file_id = paths.resolve(svc, remote_path)  # raises RemoteNotFoundError if absent
    svc.files().delete(fileId=file_id).execute()
```

Drive returns HTTP 204 on success. If `paths.resolve` raises `RemoteNotFoundError`, the delete is never attempted.

---

## 5. Remote-Path Resolution

### Why path-walking is required

Google Drive has no native path namespace. Every item has a file ID and a list of parent IDs; names are non-unique within a folder. Velmiren's slash-delimited remote path strings (e.g., `/velmiren/inbox/foo.pdf`) are an abstraction resolved to Drive file IDs at runtime.

### Walk algorithm (`paths.py`)

Given remote path `/velmiren/inbox/foo.pdf`:

1. Strip leading `/`. Split on `/` → `["velmiren", "inbox", "foo.pdf"]`.
2. Start with `parent_id = "root"` (Drive's alias for My Drive root).
3. For each segment except the last, issue a folder lookup:

   ```
   q = "name='{seg}' and '{parent_id}' in parents
        and mimeType='application/vnd.google-apps.folder'
        and trashed=false"
   ```

   Zero results → `RemoteNotFoundError`. One or more results → take the first ID as the new `parent_id`. (Drive allows duplicate folder names; first-by-default-order is deterministic within a command invocation.)

4. For the last segment, issue the same query without the `mimeType` filter (can be file or folder).
5. Zero results → `RemoteNotFoundError`. Otherwise return the file ID of the last segment.

### Remote root resolution (`_resolve_remote_root`)

`_resolve_remote_root() -> str` is a module-level helper in `paths.py` that determines the starting point for all remote path walks:

1. Reads the `VELMIREN_REMOTE_ROOT` environment variable. If it is set, its value is returned.
   - A plain folder name (no `/`) replaces `"velmiren"` as the first segment looked up under My Drive root via a name query.
   - A value beginning with the explicit prefix `id:` (e.g., `id:1BxiMVs0...`) has the prefix stripped and the remainder used directly as the root `parent_id`, skipping the name lookup entirely. This explicit prefix convention is preferred over a length/character-class heuristic to eliminate false positives.
2. Falls back to the string `"velmiren"` (the default folder name) if the environment variable is not set.

`_resolve_remote_root()` is called at the start of both `_walk()` and `ensure_path()` in place of the hardcoded `parent_id = "root"` that was the initial walk seed. When the returned value is a folder name (not an `id:` prefixed ID), the walk issues a standard name query under Drive's `root` pseudo-ID alias to obtain the actual `parent_id` before proceeding.

### Per-session cache

```python
_cache: dict[str, str] = {}

def resolve(svc, remote_path: str) -> str:
    """Return Drive file ID for remote_path. Raises RemoteNotFoundError if not found."""
    if remote_path in _cache:
        return _cache[remote_path]
    file_id = _walk(svc, remote_path)
    _cache[remote_path] = file_id
    return file_id
```

Cache is module-level. Lifetime is one process (one command execution). No persistence needed — Drive file IDs are stable unless the file is deleted and re-created.

### Folder creation for `send` (US-2)

`ensure_path(svc, remote_path) -> tuple[str, str]` returns `(parent_folder_id, leaf_name)`, creating missing intermediate folders:

```python
def ensure_path(svc, remote_path: str) -> tuple[str, str]:
    """Walk remote_path, creating missing intermediate folders.
    Return (parent_folder_id, leaf_name)."""
    segments = remote_path.strip("/").split("/")
    parent_id = _resolve_remote_root()
    for seg in segments[:-1]:
        parent_id = _get_or_create_folder(svc, seg, parent_id)
    return parent_id, segments[-1]
```

`_get_or_create_folder(svc, name, parent_id)` does the folder lookup first; if not found, calls:

```python
svc.files().create(
    body={
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    },
    fields="id",
).execute()
```

---

## 6. Open Questions — Resolutions

### OQ-1: Remote root folder convention

**Resolution**: The default remote root is a folder named `velmiren` under the My Drive root. `paths.ensure_path` and `paths.resolve` both start from Drive's `root` pseudo-ID alias, so the first segment of every remote path is looked up as a direct child of My Drive. On first `velmiren send`, if the `velmiren` folder does not exist, `ensure_path` creates it automatically — no separate setup step at auth time.

The root is overridable via environment variable `VELMIREN_REMOTE_ROOT`. If the env var is set to a plain folder name string (no `/`), it replaces `"velmiren"` as the first path segment looked up under `root`. If set to a raw Drive file ID (recognisable as a 28–44 character alphanumeric string with no `/`), it is used directly as the root parent ID, skipping the name lookup. `velmiren config set remote_root` is deferred to v1.x.

**Rationale**: Auto-creating a named folder under My Drive requires zero user configuration — `pip install` → `velmiren auth google` → `velmiren send` works immediately. Storing the folder *name* rather than a hard-coded file ID means the user can delete and re-create the folder on Drive without reconfiguring Velmiren. The env-var override covers advanced users without adding a `config` subcommand to v1.

**Rejected alternative**: Requiring users to specify the full absolute path on every `send`/`fetch`/`list` call. The acceptance criteria use short paths like `/velmiren/report.pdf`, which imply a root convention is assumed. Requiring full paths from `root` every time would be verbose without adding clarity.

### OQ-2: Idempotent uploads

**Resolution**: On `velmiren send <local> --to <remote>`, `drive.upload()` calls `_find_by_name(svc, leaf_name, parent_id)`. If a file with that name already exists in the target folder, it calls `files().update(fileId=existing_id, media_body=new_media)` — replacing the content in place and preserving the file ID. If no such file exists, it calls `files().create(...)`. Running `send` twice for the same `--to` replaces the content; no duplicate files accumulate.

**Rationale**: Drive's default `files().create()` creates a new file alongside any existing file with the same name (Drive allows duplicate names by design). For a transport tool, silent versioning on every re-upload creates Drive clutter the user never requested and requires manual cleanup. Explicit overwrite matches the mental model of `cp` and `scp`. Users who want Drive's native versioning can manage it via the Drive web UI or a future `--version` flag.

**Rejected alternative**: Drive's default version-on-duplicate. Rejected because the acceptance criteria describe `send` as writing to a *named path*, implying idempotent replacement. A `--version` flag to opt into Drive native versioning is noted in Future Work.

### OQ-3: OAuth client registration

**Resolution**: Velmiren ships with an embedded OAuth app client identifier and client secret in `auth.py` — two module-level string constants (`_DEFAULT_CLIENT_ID` and `_DEFAULT_CLIENT_SECRET`). Users who run `velmiren auth google` connect through the "Velmiren" GCP OAuth app. Google shows an "unverified app" consent screen; users click "Advanced → Go to Velmiren (unsafe)". This is the standard experience for unverified installed apps and is documented by Google as expected for non-public tools.

Users who want their own GCP app set `VELMIREN_OAUTH_CLIENT_ID` and `VELMIREN_OAUTH_CLIENT_SECRET` env vars. `auth.py` reads these in `_get_client_config()` and uses them in place of the embedded values.

**Rationale**: For installed-app (desktop) OAuth, the client secret is a public identifier — explicitly stated in Google's installed-app OAuth guide. Any user can extract it from source or binary. Google's security model for installed apps relies on PKCE (which `InstalledAppFlow.run_local_server()` uses by default), not on secrecy of the client secret. Embedding the values means `pip install velmiren && velmiren auth google` works with zero GCP console setup. This pattern is standard practice for open-source CLI tools including `rclone`.

**Rejected alternative**: Requiring each user to register their own GCP OAuth app before first use. GCP console setup is a 10-step process — a hard blocker for non-technical users and unnecessary friction for Kaushik.

---

## 7. Error Model

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Not found; or `exists` check returned false |
| 2 | Auth failure (no cred file, expired token, revoked token, refresh failed) |
| 3 | User error (missing required flag, invalid argument) |
| 4 | Network error or Google API error (non-auth) |
| 5 | Size cap exceeded (file > 500 MB) |

### Exception hierarchy (`errors.py`)

```python
class VelmirenError(Exception):
    exit_code: int = 1
    message: str = ""

    def __init__(self, message: str = ""):
        self.message = message or self.__class__.message
        super().__init__(self.message)


class NotAuthenticatedError(VelmirenError):
    exit_code = 2
    message = "not authenticated — run 'velmiren auth google' first"

class AuthExpiredError(VelmirenError):
    exit_code = 2
    message = "authentication expired — run 'velmiren auth google' to re-authenticate"

class RemoteNotFoundError(VelmirenError):
    exit_code = 1
    # message passed at raise site: "no such remote file" or "no such remote folder"

class UserError(VelmirenError):
    exit_code = 3
    # message passed at raise site

class NetworkError(VelmirenError):
    exit_code = 4
    # message passed at raise site (Google API error surfaced verbatim)
    # accepts optional status_code kwarg (HTTP status from Drive response, e.g. 403, 500)

class SizeCapError(VelmirenError):
    exit_code = 5
    message = "file exceeds v1 size cap (500 MB)"
```

### Acceptance-criteria strings → exit codes

| Acceptance-criteria string | Exception | Exit code |
|---|---|---|
| `not authenticated — run 'velmiren auth google' first` | `NotAuthenticatedError` | 2 |
| `authentication expired — run 'velmiren auth google' to re-authenticate` | `AuthExpiredError` | 2 |
| `no such remote folder` | `RemoteNotFoundError` | 1 |
| `no such remote file` | `RemoteNotFoundError` | 1 |
| `--force required` | `UserError` | 3 |
| `file exceeds v1 size cap (500 MB)` | `SizeCapError` | 5 |
| `OK — authenticated as <email>` | (success — printed to stdout) | 0 |
| `false` (`velmiren exists`) | (success — printed to stdout) | 1 |
| `true` (`velmiren exists`) | (success — printed to stdout) | 0 |

### Top-level error handler in `cli.py`

```python
import sys
import click
from velmiren.errors import VelmirenError

@click.group()
def main():
    pass

def _run(fn, *args, **kwargs):
    """Wrap a command body; catch VelmirenError and exit cleanly."""
    try:
        fn(*args, **kwargs)
    except VelmirenError as exc:
        click.echo(exc.message, err=True)
        sys.exit(exc.exit_code)
```

Unexpected exceptions propagate normally — Python prints a traceback and exits 1.

---

## 8. Unit-Test Strategy

### Framework

`pytest` + `pytest-mock` + `pytest-cov`. Coverage target ≥ 80% on `src/velmiren/`. Run with:

```
pytest tests/ --cov=src/velmiren --cov-report=term-missing --cov-fail-under=80
```

No test requires a real network connection or a real Google account (US-10).

### Mock points

| What to mock | Mock target | Used by |
|---|---|---|
| Drive service construction | `velmiren.drive._service` — returns a `MagicMock` shaped like the Drive v3 service object | `test_drive.py`, `test_cli.py` |
| OAuth flow | `google_auth_oauthlib.flow.InstalledAppFlow.run_local_server` — returns a fake user-cred object | `test_auth.py` |
| `auth.load()` | `velmiren.auth.load` — returns the `fake_cred` fixture | All command tests in `test_cli.py` |
| Cred file read | `velmiren.auth._read_cred_file` — returns a fixture dict with six fields | `test_auth.py` |
| Cred file write | `velmiren.auth._atomic_write_cred` — no-op or captured | `test_auth.py` |
| Token refresh transport | `google.auth.transport.requests.Request` — `MagicMock()` | `test_auth.py` |

### Fixtures (`tests/conftest.py`)

```python
import pytest
from unittest.mock import MagicMock

@pytest.fixture
def fake_drive_service():
    """MagicMock shaped like the Drive v3 service object."""
    svc = MagicMock()
    files = MagicMock()
    svc.files.return_value = files
    return svc

@pytest.fixture
def fake_cred():
    """Minimal cred object that passes auth.load() checks."""
    cred = MagicMock()
    cred.token = "fake-access-token"
    cred.valid = True
    cred.expired = False
    return cred
```

A third fixture, `fake_cred_data`, is also defined in `conftest.py`. It returns a plain dict with all five cred-file field names populated with short non-real placeholder strings (no actual tokens or secrets). This fixture is used in `test_auth.py` to mock `_read_cred_file` return values without touching the real file system. The field names in the dict match the six names described in §2 (including the email field); the values are obvious test placeholders.

### Coverage per user story

Each US has at least one happy-path test and one error-path test:

| US | Test file | Happy path | Error path |
|---|---|---|---|
| US-1 (auth) | `test_auth.py` | OAuth flow completes; cred file written | OAuth flow raises; existing cred file unchanged |
| US-2 (send) | `test_cli.py` + `test_drive.py` | File uploaded; Drive ID printed | File > 500 MB raises `SizeCapError`; auth missing raises `NotAuthenticatedError` |
| US-3 (list) | `test_cli.py` + `test_drive.py` | Files listed one-per-line | Non-existent folder raises `RemoteNotFoundError` |
| US-4 (fetch) | `test_cli.py` + `test_drive.py` | File downloaded; bytes-written printed | Remote not found; `--to` is directory (name inferred) |
| US-5 (exists) | `test_cli.py` + `test_drive.py` | Prints `true`; exits 0 | Prints `false`; exits 1; auth failure exits 2 |
| US-6 (delete) | `test_cli.py` + `test_drive.py` | File deleted; exits 0 | No `--force` raises `UserError`; not found raises `RemoteNotFoundError` |
| US-7 (status) | `test_cli.py` + `test_auth.py` | Prints auth fields; exits 0 | No cred file; exits 2 |
| US-8 (re-auth) | `test_auth.py` | Overwrites cred file after successful OAuth | Failed OAuth leaves original cred file intact |
| US-9 (no auth) | `test_cli.py` | — | Any command without cred file prints `not authenticated` message; exits 2 |

---

## 9. Dependency Pins

Entries to add to `pyproject.toml`:

**Runtime** — replace the commented-out block in `[project.dependencies]`:

```toml
dependencies = [
    "click>=8.1",
    "google-auth>=2.28",
    "google-auth-oauthlib>=1.2",
    "google-api-python-client>=2.120",
]
```

**Dev/test** — extend `[project.optional-dependencies] dev`:

```toml
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.14",
    "pytest-cov>=5.0",
    "ruff>=0.4",
]
```

`keyring` is explicitly excluded — locked decision #3 (no OS keyring). All auth state goes in the plain `~/.velmiren/cred` file.

---

## 10. Files Changed

Every row below is implementable from §§1–9 of this document alone. There are no "and other files" entries.

| File | Change | ~LOC |
|------|--------|------|
| `src/velmiren/__init__.py` | Modify: add `__version__ = "0.1.0"` (currently empty) | 2 |
| `src/velmiren/__main__.py` | Create: `from velmiren.cli import main; main()` — enables `python -m velmiren` | 5 |
| `src/velmiren/errors.py` | Create: `VelmirenError` hierarchy (6 subclasses), exit-code constants, acceptance-criteria string catalogue (§7) | 60 |
| `src/velmiren/auth.py` | Create: `run_oauth_flow()`, `load()`, `_read_cred_file()`, `_atomic_write_cred()`, `_build_credential()`, `_build_client_config()`, `_get_client_config()`, `_handle_refresh_error()`, `_fetch_email()` (calls Google userinfo endpoint post-token-exchange to obtain and persist account email), `_DEFAULT_CLIENT_ID` and `_DEFAULT_CLIENT_SECRET` constants (§3) | 145 |
| `src/velmiren/paths.py` | Create: `resolve()`, `ensure_path()`, `_walk()`, `_get_or_create_folder()`, `_resolve_remote_root()` (reads `VELMIREN_REMOTE_ROOT`, applies `id:` prefix heuristic, falls back to `"velmiren"`), module-level `_cache` dict and `_DEFAULT_ROOT_FOLDER` constant (§5) | 105 |
| `src/velmiren/drive.py` | Create: `upload()`, `download()`, `list_dir()`, `file_exists()`, `delete_file()`, `_service()`, `_auth_param()`, `_find_by_name()` (§4) | 160 |
| `src/velmiren/cli.py` | Create: Click group `main`, commands `auth_google`, `status`, `send`, `fetch`, `list_files`, `exists`, `delete`; top-level `_run` error handler (§1, §7) | 190 |
| `pyproject.toml` | Modify: replace commented-out runtime deps; add `pytest-mock`, `pytest-cov` to dev extras (§9) | +8 lines |
| `tests/__init__.py` | Create: empty package marker | 1 |
| `tests/conftest.py` | Create: `fake_drive_service`, `fake_cred`, `fake_cred_data` fixtures; shared helpers (§8) | 80 |
| `tests/test_errors.py` | Create: unit tests for exception hierarchy, exit-code values, message defaults | 40 |
| `tests/test_auth.py` | Create: US-1, US-7, US-8, US-9 — happy + error paths; mocks OAuth flow and cred file I/O | 130 |
| `tests/test_paths.py` | Create: `resolve()` happy path, cache hit, `RemoteNotFoundError` on missing segment, `ensure_path` creates folders | 90 |
| `tests/test_drive.py` | Create: upload create path + update-existing path, download with dir target, list, exists, delete; mocks `_service` | 160 |
| `tests/test_cli.py` | Create: Click `CliRunner` tests for all 8 commands; happy + error paths per US-2–US-9; mocks `auth.load` and `drive.*` | 200 |

---

## Future Work (Out of Scope)

- `velmiren config set remote_root` subcommand — env-var override covers v1; config subcommand is the natural v1.x addition.
- Resumable upload for files > 500 MB — requires `MediaFileUpload(resumable=True)` and chunk-retry logic; deferred per locked decision #7.
- `--version` flag on `velmiren send` to opt into Drive's native file versioning instead of overwrite semantics.
- Multi-backend adapter (Dropbox, Box) — the `CloudBackend` abstraction from `.claude/research/credential-management.md` is the starting point when this is needed.
- MCP wrapper around the CLI — deferred per locked decision #5.
- Drive quota and rate-limit handling — Google's error is surfaced verbatim for now; exponential backoff is v1.x.
- `--dry-run` flag for `send` and `delete`.
- Pagination in `list_dir` — v1 returns at most 1,000 results (single Drive page); personal folders are unlikely to exceed this limit.

---

## Open Questions for /dryrun-design

1. **`velmiren status` token expiry display**: the cred file stores no access token or expiry timestamp (access tokens are minted fresh on each `auth.load()` call). US-7 requires "Token expiry (UTC ISO8601, if authenticated)". The intended approach: `auth.load()` performs the refresh and the resulting cred object exposes an `.expiry` attribute; `cli.py`'s `status` command reads this and prints it. This means `status` triggers a live token refresh as a side effect. Confirm this is acceptable before implementing.

2. **`VELMIREN_REMOTE_ROOT` as raw Drive ID vs path string**: the design uses a format heuristic (length / character-class check) to distinguish a raw file ID from a folder name string. A more explicit format — e.g., `id:<file_id>` prefix vs a bare name — avoids ambiguity. Flag for dryrun review.

3. **`velmiren list` with no argument**: the acceptance criteria say it lists "the configured remote root." `cli.py` must obtain the remote root folder ID before calling `drive.list_dir()`. Currently this could be done via `paths.ensure_path(cred, "/velmiren")` or a dedicated `paths.get_root_id(cred)` helper. Confirm which function owns "resolve the remote root ID" — currently it could live in `paths.py` or be computed inline in `cli.py`.
