# Credential Management Research — Velmiren v1

_Last updated: 2026-04-21_ · _Reformatted post-decisions._

## TL;DR

`keyring` v25.7.0 is the right cross-platform store. On Windows (v1 target) its blob limit is **2,560 bytes** (`CRED_MAX_CREDENTIAL_BLOB_SIZE`), which a full `google-auth` JSON blob with an access token exceeds — writes silently fail with opaque error **1783**. Store **only the refresh-token string** (~200 bytes) in keyring; keep non-sensitive metadata on disk at `~/.velmiren/accounts.json`.

Google OAuth access tokens last **3,600 s**; refresh tokens are long-lived but have 6 revocation triggers. Dropbox (future backend) needs `token_access_type=offline` to issue a refresh token and returns a uniform 401 for both expired-access and revoked-refresh — requires attempt-refresh-on-401 logic. A single `CloudBackend.auth()` interface is viable with per-adapter quirk encapsulation.

---

## Locked Decisions (April 21, 2026)

| # | Decision | Implication |
|---|---|---|
| 1 | **Storage path**: `~/.velmiren/accounts.json` | Cross-platform via `os.path.expanduser("~")`. Windows: `C:\Users\<user>\.velmiren\`. Linux/macOS: `$HOME/.velmiren/`. |
| 2 | **Refresh-token-only in keyring** | Must verify with a test before commit — store + reload via fresh process + `Credentials.from_authorized_user_info` + `credentials.refresh()`. |
| 3 | **Box dropped from v1** | Google Drive only for v1. Dropbox as future candidate. Box findings retained in Appendix A. |
| 4 | **Single-system scope (Kaushik's Windows PC)** | No headless/CI/NAS support in v1. Linux/Docker findings retained in Appendix B. |

---

## 1. keyring Python Library

### Current version

**25.7.0** (released 2025-11-16). Requires Python ≥ 3.9.
Source: https://pypi.org/project/keyring/

### Windows backend (v1 target)

`keyring.backends.Windows.WinVaultKeyring` — uses `CredRead`/`CredWrite` via `pywin32`. Auto-selected on Windows. No extra configuration needed.

### Default backend selection

`get_all_keyring()` filters to backends whose `.priority` does not raise `RuntimeError`, then picks the highest priority. Override via `PYTHON_KEYRING_BACKEND` env var, `keyringrc.cfg`, or programmatic `keyring.set_keyring(...)`.

### Token / blob size — critical finding

**Windows Credential Manager hard cap: `CRED_MAX_CREDENTIAL_BLOB_SIZE` = 5 × 512 = 2,560 bytes.**

Defined in `wincred.h`. The keyring Windows backend applies no pre-check — passes data straight to `CredWrite()`. When the blob exceeds 2,560 bytes, Windows returns error **1783** (`ERROR_STUB_RECEIVED_BAD_DATA`), an opaque error that does not mention the size limit.

Tracked in:
- keyring issue #355 (closed 2020-04-30): "Obscure error when credential is longer than allowed" — https://github.com/jaraco/keyring/issues/355
- keyring issue #540 (open, 2021-11-09): "Support longer passwords in Windows" — https://github.com/jaraco/keyring/issues/540

PR #544 (sharding proposal) is **not merged** as of 2026-04-21. Strings are stored as UTF-16 (2 bytes per char), so a 1,280-character string already hits the limit.

Typical OAuth blob sizes:

| Storage shape | Approx size | Windows fit |
|---|---|---|
| Refresh token string only | ~100–200 chars = 200–400 bytes UTF-16 | **SAFE** |
| `Credentials.to_json()` without access token | 500–900 bytes | Borderline |
| `Credentials.to_json()` with access token | 1,500–2,500 bytes | **UNSAFE — hits 1783** |

**Conclusion**: Store only the refresh-token string in keyring. Never the full JSON blob.

### Security model (Windows)

Blobs encrypted with DPAPI using the current user's logon key. Per-user; another user cannot read. Any process running as the same user CAN read — Windows does not enforce per-application ACLs on `CRED_TYPE_GENERIC` entries. Equivalent threat model to browser session cookies — accepted industry norm for desktop OAuth.

### Multi-process contention

`CredWrite` is atomic. Concurrent writes: last-write-wins, no corruption, no merge. Read during write: old or new value, never corrupt. No built-in locking in the keyring library.

---

## 2. Windows Credential Manager (primary target)

### CREDENTIAL structure (`wincred.h`)

| Field | Limit |
|---|---|
| `TargetName` (`CRED_TYPE_GENERIC`) | 32,767 characters |
| `CredentialBlob` | **2,560 bytes** (`CRED_MAX_CREDENTIAL_BLOB_SIZE`) |
| `UserName` | 513 characters |
| `Comment` | 256 characters |
| Persist values | `SESSION=1`, `LOCAL_MACHINE=2`, `ENTERPRISE=3` |

Source: https://learn.microsoft.com/en-us/windows/win32/api/wincred/ns-wincred-credentialw

### Persistence choice

- `CRED_PERSIST_SESSION` — survives only current login. Not suitable.
- `CRED_PERSIST_LOCAL_MACHINE` — persists across reboots, this user on this machine only. **Correct choice for Velmiren.**
- `CRED_PERSIST_ENTERPRISE` — roams via Active Directory. Not useful for home/indie users.

The keyring Windows backend defaults to `ENTERPRISE`, falling back silently to `LOCAL_MACHINE` on Home editions.

### Survival scenarios

| Scenario | Survival |
|---|---|
| Windows Update / restart | ✅ Survives |
| User password change | ✅ DPAPI re-encrypts automatically |
| Profile backup/restore (same machine) | ✅ If profile restored intact |
| Profile migration to new machine | ❌ DPAPI is machine+user-bound |
| Laptop failure / SSD replacement | ❌ Lost |
| Windows clean reinstall | ❌ Lost |

### CredWrite error codes

Source: https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-credwritew

| Code | Meaning | When |
|---|---|---|
| `ERROR_NO_SUCH_LOGON_SESSION` | — | Network logon sessions lack a credential set |
| `ERROR_INVALID_PARAMETER` | — | Protected field mismatch on existing entry |
| `ERROR_BAD_USERNAME` | — | Malformed `UserName` field |
| **1783** | `ERROR_STUB_RECEIVED_BAD_DATA` | **Opaque; typically means blob > 2,560 bytes** |

---

## 3. Google OAuth 2.0 Token Management (v1 backend)

### Token lifecycles

| Token | Lifetime |
|---|---|
| Access token | **3,600 s (1 hour)** — `expires_in: 3600` in response |
| Refresh token | Long-lived; no fixed expiry, but 6 revocation triggers |
| Refresh token (GCP test mode, basic scopes only) | 7 days |

Documented sizes: access token up to 2,048 bytes; refresh token up to 512 bytes.
Source: https://developers.google.com/identity/protocols/oauth2

### Refresh token revocation triggers

1. User revokes app access via Google Account settings.
2. Token unused for **6 months**.
3. User changed Google password AND token used Gmail scopes.
4. User exceeded **100 refresh tokens per client ID** cap (oldest silently revoked).
5. Admin-level restriction applied to the service.
6. GCP session length policy exceeded.

### Token refresh

POST to `https://oauth2.googleapis.com/token` with `grant_type=refresh_token`. Response includes new `access_token`, `expires_in: 3600`, optionally a new `id_token`. **The refresh token is NOT rotated** — Google does not issue a new refresh token on each refresh. (This differs from Box, which rotates on every use.)

### Refresh failure

HTTP 400 body contains `error=invalid_grant` with description like "Token has been expired or revoked." The `google-auth` library raises `google.auth.exceptions.RefreshError`. `invalid_grant` is **not retryable** — it's a terminal signal requiring user re-authentication.

Source: https://github.com/googleapis/google-auth-library-python/blob/main/google/oauth2/_client.py

### Scope changes

Include `include_granted_scopes=true` in the new auth request to accumulate previously granted scopes. Check `granted_scopes` on the returned credentials — if a required scope wasn't granted, degrade gracefully.

### Offline access

`access_type=offline` on the authorization URL is mandatory — without it, no refresh token is issued.

### `google-auth` Credentials object

Fields in `google.oauth2.credentials.Credentials`:

- `token` — current access token (may be `None`)
- `refresh_token` — long-lived token
- `token_uri` — usually `https://oauth2.googleapis.com/token`
- `client_id`, `client_secret` — OAuth app credentials
- `scopes` — frozenset of requested scopes
- `granted_scopes` — frozenset actually granted
- `expiry` — UTC datetime of access token expiry
- `id_token` — OpenID Connect JWT (if `openid` scope requested)

Serialization: `credentials.to_json()` / `Credentials.from_authorized_user_info(json.loads(...))`. Required deserialization fields: `refresh_token`, `client_id`, `client_secret`. `token_uri` defaults to the Google endpoint if absent.

**Do not store the full `to_json()` blob in Windows Credential Manager** (exceeds 2,560 bytes with an access token included).

### Logging risk

`google.oauth2._client.py` — no logging statements. Token values never logged. `google.oauth2.reauth` writes status strings to stderr, not token values.

---

## 4. CloudBackend Adapter Abstraction

### v1 scope: Google Drive only. Dropbox evaluated for future.

Box has been **dropped from v1** (retained in Appendix A for future reference).

### Side-by-side comparison (Google Drive v1 vs Dropbox future)

| Property | Google Drive (v1) | Dropbox (future) |
|---|---|---|
| Auth URL | `https://accounts.google.com/o/oauth2/v2/auth` | `https://www.dropbox.com/oauth2/authorize` |
| Required auth params | `client_id`, `redirect_uri`, `response_type=code`, `scope`, `access_type=offline` | `client_id`, `response_type=code`, `token_access_type=offline` |
| Scope format | Full URIs, space-separated: `https://www.googleapis.com/auth/drive` | Short names: `files.content.write`, `account_info.read` |
| PKCE | Recommended for desktop | **Required, S256** |
| Token endpoint | `https://oauth2.googleapis.com/token` | `https://api.dropboxapi.com/oauth2/token` |
| Offline-access trigger | `access_type=offline` on auth URL | `token_access_type=offline` on auth URL |
| Access-token lifetime | **3,600 s** | Short-lived (exact duration not published) |
| Refresh-token lifetime | Long-lived, 6 revocation triggers | Long-lived, no published expiry |
| Refresh rotation | **No** | **No** |
| Expired-access error | HTTP 401 | HTTP 401 |
| Revoked-refresh error | HTTP 400, `error=invalid_grant` | HTTP 401 (no sub-error code) |
| Distinguish revoked vs expired | ✅ `invalid_grant` is specific | ❌ uniform 401 — must attempt refresh and escalate if it also fails |
| Device code flow | ✅ Full support | ❌ Not documented |

Sources: Google OAuth docs above; Dropbox OAuth guide https://developers.dropbox.com/oauth-guide, PKCE blog https://dropbox.tech/developers/pkce--what-and-why-, error handling https://developers.dropbox.com/error-handling-guide

### Proposed interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class TokenBundle:
    access_token: str | None
    refresh_token: str
    expiry: datetime | None
    scopes: frozenset[str]
    raw_metadata: dict  # adapter-specific fields


class CloudBackend(ABC):
    """Abstract interface for a cloud storage backend."""

    @property
    @abstractmethod
    def backend_id(self) -> str:
        """Short identifier used for keyring namespacing (e.g., 'google-drive')."""

    @property
    @abstractmethod
    def supports_device_flow(self) -> bool: ...

    @property
    @abstractmethod
    def requires_pkce(self) -> bool: ...

    @abstractmethod
    def auth_url(self, scopes: frozenset[str]) -> tuple[str, str | None]:
        """Return (authorization URL, PKCE code_verifier or None)."""

    @abstractmethod
    def exchange_code(self, code: str, code_verifier: str | None) -> TokenBundle: ...

    @abstractmethod
    def refresh(self, bundle: TokenBundle) -> TokenBundle:
        """Returns a NEW bundle. Raises AuthExpiredError (non-retryable) or TransientAuthError (retryable)."""

    @abstractmethod
    def upload(self, local_path: str, remote_path: str) -> None: ...

    @abstractmethod
    def download(self, remote_path: str, local_path: str) -> None: ...

    @abstractmethod
    def list(self, remote_dir: str | None = None) -> list[dict]: ...

    @abstractmethod
    def exists(self, remote_path: str) -> bool: ...

    @abstractmethod
    def delete(self, remote_path: str) -> None: ...
```

### Interface contract

1. `auth_url()` returns `(url, code_verifier_or_None)` — callers remain PKCE-agnostic.
2. `refresh()` always returns a new `TokenBundle` — callers replace, never mutate in place.
3. `refresh()` raises `AuthExpiredError` for non-retryable failures (`invalid_grant`, 401 on refresh attempt itself).
4. `refresh()` raises `TransientAuthError` for network/5xx — safe to retry with backoff.
5. `supports_device_flow` lets the caller choose between browser launch and device code display.
6. Scope mapping is adapter-internal: the caller passes abstract capability names; the adapter translates to backend-native scope strings.
7. Error disambiguation (Dropbox uniform 401) is encapsulated in the adapter — attempt refresh on 401, escalate only if that also fails.

### Verdict

Interface is viable for Google Drive + Dropbox without Box-specific contortions. If Box is added later, the single-use rotation concern stays inside the Box adapter (needs lock file), not in the shared interface.

---

## 5. Operational Gotchas (Windows-only v1 scope)

### 5.1 Namespace collisions in keyring

Use fully namespaced service names for keyring entries:

- `velmiren/google-drive`
- `velmiren/dropbox` (future)

Bare short names (`google`, `drive`, `box`) collide with other Python tools (`gcloud` CLI, VS Code extensions, etc.). During revocation, call `keyring.delete_password(service, username)` explicitly.

### 5.2 Backup and disaster recovery

Tokens in Windows Credential Manager are DPAPI-encrypted with machine+user-bound keys. Not portable, not backable.

Recovery design:

- At startup, if `keyring.get_password()` returns `None` or raises: transition to "not connected" state.
- Surface a reconnect prompt: "Your Google Drive connection needs to be re-established."
- Never treat absent stored tokens as a fatal application error.
- No user data is lost — only the authorization must be re-done.

### 5.3 Logging — token-leak risk

| Library | Logs token values? | Notes |
|---|---|---|
| `google-auth` (`_client.py`) | No | No logging module imported. Verified in source. |
| `google-auth` (`reauth.py`) | No | Status strings to stderr only. |
| `dropbox` Python SDK | No | Logs "Refreshing access token" message, not the value. |
| `keyring` | No | Does not log stored or retrieved values. |
| `requests` / `urllib3` | **Yes at DEBUG level** | Logs full HTTP headers including `Authorization: Bearer <token>`. |

**Required mitigation** — add unconditionally to Velmiren's logging setup:

```python
import logging
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
```

Apply regardless of root logger level.

---

## Recommendations for Velmiren v1

### Credential storage layout

**In keyring** (sensitive only):

```
service = f"velmiren/{backend_id}"
username = user_email
password = refresh_token_string    # ~200 bytes, well under the 2,560 limit
```

**On disk** (non-sensitive metadata), at `~/.velmiren/accounts.json`:

```json
{
  "google-drive": {
    "user_email": "hazra.kaushik@gmail.com",
    "client_id": "<oauth app client id>",
    "token_uri": "https://oauth2.googleapis.com/token",
    "scopes": ["https://www.googleapis.com/auth/drive.file"],
    "last_authorized_at": "2026-04-21T15:00:00Z"
  }
}
```

**Do NOT store** `client_secret` or `refresh_token` in this file.

### Startup flow

1. Read `~/.velmiren/accounts.json` — get non-sensitive metadata.
2. `keyring.get_password("velmiren/google-drive", user_email)` — get refresh token string.
3. Construct `Credentials(token=None, refresh_token=<from keyring>, ...metadata...)`.
4. Call `credentials.refresh(Request())` to mint a fresh access token.
5. Proceed with API calls.

### Verification task (before commit)

Before committing to refresh-only storage, run a small end-to-end test:

1. Perform OAuth flow, capture the `Credentials` object.
2. Extract refresh token, store via `keyring.set_password("velmiren/test", "hazra", refresh_token)`.
3. Spawn a fresh Python process (not just a new function call — must clear all in-memory state).
4. In the fresh process: read the refresh token back, construct `Credentials.from_authorized_user_info({...metadata..., "refresh_token": <from keyring>})`, call `credentials.refresh(Request())`.
5. Confirm a valid access token is minted and a trivial API call succeeds (e.g., `drive.about.get`).

If that passes cleanly, refresh-only storage is proven. If it fails, investigate and adjust before building on it.

### Refresh-failure handling

```python
from google.auth.exceptions import RefreshError

try:
    credentials.refresh(request)
except RefreshError as e:
    if "invalid_grant" in str(e):
        # Non-retryable. Token revoked or expired beyond refresh.
        raise AuthExpiredError("Please re-authorize this account") from e
    # Network/5xx — retry with backoff
    raise TransientAuthError(str(e)) from e
```

### Red flags (ordered by risk)

1. **Windows 2,560-byte limit with opaque error 1783.** Storing the full `to_json()` blob silently fails. **Store only the refresh-token string.** This likely also explains the FPA YouTube OAuth bug (Taskyn 195a88a0).
2. **Dropbox uniform 401** (future backend). Must attempt refresh on 401 and escalate only if that also fails.
3. **`macOS` no-prompt keychain access** (if ever cross-platform). Any Python script on the system can read tokens. Inherent to macOS generic keychain; acknowledge in threat model.
4. **Service-name namespace collisions.** Use `velmiren/{backend_id}` unconditionally.
5. **`requests` / `urllib3` DEBUG logging leaks Bearer tokens.** Suppress at WARNING unconditionally.

---

## Open Questions (remaining after April 21 decisions)

1. **`google-auth` version pinning policy.** The `to_json()` / `from_authorized_user_info()` format must remain stable across library updates. What's our pinning policy, and how is migration tested when we upgrade?
2. **Real-time revocation (Google RISC).** Google Cross-Account Protection can push revocation events via webhook (https://developers.google.com/identity/protocols/risc). Worth implementing at v1 (requires a server-side webhook endpoint), or is detect-on-next-use sufficient for a local-user desktop tool? Current lean: detect-on-next-use — we're not running a public webhook listener on Kaushik's PC.

---

## Appendix A — Future Backends (post-v1)

### Box (deferred from v1)

Box was evaluated in the original research but **dropped from v1 scope** on April 21. Findings retained here for future reference.

**Key Box-specific characteristics:**

- Auth URL: `https://account.box.com/api/oauth2/authorize`
- Scope format: short names (`root_readwrite`, `item_upload`, `item_download`)
- Access-token lifetime: ~3,600 s
- Refresh-token lifetime: **60 days, single-use rotation**
- **Refresh-token rotation: Yes** — each use invalidates the old one and returns a new one. Must persist immediately.
- PKCE: not documented in public API
- Device flow: not documented

**Critical race condition**: Two processes sending the same Box refresh token simultaneously — one succeeds with new access + new refresh; the other receives `invalid_grant` (single-use consumed). If the winner crashes before persisting the new refresh token, the user is **permanently locked out**.

**Mitigation (if added later)**: Use a lock file (e.g., `~/.velmiren/box-token.lock`) to serialize refresh operations. Only one process may refresh Box tokens at a time. Write-then-confirm semantics on the new token.

Sources: https://developer.box.com/reference/post-oauth2-token/, https://developer.box.com/guides/authentication/tokens/refresh/, https://developer.box.com/reference/get-authorize/

---

## Appendix B — Cross-platform Expansion (post-v1)

v1 runs on Kaushik's Windows PC only. If Velmiren later needs to run on Linux, macOS, or headless/CI/Docker, these findings apply.

### keyring backends — other platforms

| Platform | Backend | Notes |
|---|---|---|
| macOS | macOS Keychain (`keyring.backends.macOS.Keyring`) | Requires macOS 11+ with Python 3.8.7+ universal2 binary. No documented byte limit for generic passwords. |
| Linux/Freedesktop | Secret Service via `secretstorage` | GNOME Keyring / libsecret. Requires D-Bus session bus. |
| Linux/KDE | `KWallet` (`keyring.backends.kwallet.DBusKeyring`) | Requires `dbus-python` (system package, not pip). |

### Headless / CI / Docker behavior

On headless Linux without X11 or a D-Bus session bus:

- Secret Service raises `RuntimeError: The Secret Service daemon is not available`.
- KWallet raises a similar error.
- If no viable backend: `NoKeyringError`.

In Docker without `--privileged`: `gnome-keyring-daemon: Operation not permitted` (issue #733, open Nov 2025).

**Workarounds:**

- Start D-Bus session: `dbus-run-session -- python app.py`.
- `keyrings.alt.file.EncryptedKeyring` — AES256-CFB + PBKDF2, requires `pycryptodome`. Prompts once for master password. File: `crypted_pass.cfg`.
- `keyrings.alt.file.PlaintextKeyring` — plaintext file `keyring_pass.cfg`. **Dev/CI only** — not for real secrets.
- `PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring` — disables keyring entirely.

`keyrings.alt` v5.0.2 (2024-08-14) is the package. Source: https://pypi.org/project/keyrings.alt/

### Device authorization flow (RFC 8628) — for headless browsers

Google supports the OAuth 2.0 Device Authorization Grant:

1. `POST https://oauth2.googleapis.com/device/code` with `client_id` and `scope`.
2. Receive: `user_code`, `verification_url`, `device_code`, `interval`, `expires_in`.
3. Display `user_code` and `verification_url` in the terminal.
4. Poll `https://oauth2.googleapis.com/token` with `grant_type=urn:ietf:params:oauth:grant-type:device_code` at the specified interval.
5. On user approval: receive `access_token` and `refresh_token`.

Source: https://developers.google.com/identity/protocols/oauth2/limited-input-device

Dropbox has no documented device authorization flow. For headless Dropbox: pre-authorize on a browser-capable machine and transfer the refresh token, or SSH-tunnel a loopback port.

---

## Sources

- python-keyring GitHub: https://github.com/jaraco/keyring
- keyring issues #355, #540, #569, #679, #733: https://github.com/jaraco/keyring/issues
- keyring backend.py: https://github.com/jaraco/keyring/blob/main/keyring/backend.py
- keyring Windows.py: https://github.com/jaraco/keyring/blob/main/keyring/backends/Windows.py
- keyrings.alt file.py: https://github.com/jaraco/keyrings.alt/blob/main/keyrings/alt/file.py
- keyrings.alt PyPI: https://pypi.org/project/keyrings.alt/
- Windows CREDENTIAL struct: https://learn.microsoft.com/en-us/windows/win32/api/wincred/ns-wincred-credentialw
- Windows CredWrite API: https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-credwritew
- Windows Credential Guard: https://learn.microsoft.com/en-us/windows/security/identity-protection/credential-guard/how-it-works
- Google OAuth 2.0 overview: https://developers.google.com/identity/protocols/oauth2
- Google OAuth 2.0 web server flow: https://developers.google.com/identity/protocols/oauth2/web-server
- Google OAuth 2.0 native/desktop: https://developers.google.com/identity/protocols/oauth2/native-app
- Google OAuth 2.0 device flow: https://developers.google.com/identity/protocols/oauth2/limited-input-device
- Google Drive scopes: https://developers.google.com/identity/protocols/oauth2/scopes
- google-auth credentials.py: https://github.com/googleapis/google-auth-library-python/blob/main/google/oauth2/credentials.py
- google-auth _client.py: https://github.com/googleapis/google-auth-library-python/blob/main/google/oauth2/_client.py
- google-auth reauth.py: https://github.com/googleapis/google-auth-library-python/blob/main/google/oauth2/reauth.py
- Dropbox OAuth guide: https://developers.dropbox.com/oauth-guide
- Dropbox PKCE blog: https://dropbox.tech/developers/pkce--what-and-why-
- Dropbox error handling guide: https://developers.dropbox.com/error-handling-guide
- Dropbox Python SDK: https://github.com/dropbox/dropbox-sdk-python
- Box OAuth2 token endpoint: https://developer.box.com/reference/post-oauth2-token/
- Box refresh tokens guide: https://developer.box.com/guides/authentication/tokens/refresh/
- Box authorize endpoint: https://developer.box.com/reference/get-authorize/
- Box OAuth2 without SDK: https://developer.box.com/guides/authentication/oauth2/without-sdk/
