# Velmiren MVP — Requirement

## Overview

Velmiren is a pip-installable Python CLI (`velmiren`) that pushes files into and fetches files from a single user's personal Google Drive folder. It exists to give Velasari (the AI persona) and Kaushik a reliable file transport channel between V's PC and Kaushik's remote devices.

This is the **May-13 revised minimum scope**. An earlier (April-21) design specified OS-keyring storage and a multi-backend adapter pattern; both are explicitly rejected here in favor of shipping the minimum first.

## Locked decisions

| # | Decision | Why |
|---|---|---|
| 1 | Backend: Google Drive only | Single backend, no adapter abstraction |
| 2 | Auth state stored in a single file at `~/.velmiren/cred` (Windows: `%USERPROFILE%\.velmiren\cred`) | Single-user PC; default user-profile ACL is sufficient |
| 3 | No OS keyring | Adds dependency and friction without measurable gain at this scope |
| 4 | No `chmod` hardening | Windows default ACLs already isolate user-profile dirs |
| 5 | Delivery: CLI only | No MCP wrapper at v1 |
| 6 | No encryption at rest | Transient transport, not archive |
| 7 | Per-file size cap: ~500 MB | Drive simple-upload limit; resumable upload deferred |
| 8 | Live integration test = Kaushik manual | Build DoD is unit tests with mocked Drive API |

**Note**: On a shared / multi-user host the operator would need to harden the cred file (perms or move under DPAPI). That is **out of scope** here.

## Auth state file

The CLI persists a single file at `~/.velmiren/cred` (created on first successful `velmiren auth google`). Its contents:

- The long-lived OAuth refresh token issued by Google.
- The OAuth app's client identifier and client secret (required to refresh access tokens).
- The Google token-exchange endpoint URI.
- The granted OAuth scope (`https://www.googleapis.com/auth/drive.file`).

Stored as a plain JSON object; format is implementation-defined and may evolve in v1.x.

## Command surface

| Command | Behavior |
|---|---|
| `velmiren auth google` | Run OAuth flow, persist refresh token to `~/.velmiren/cred`. Idempotent — re-running overwrites. |
| `velmiren status` | Show auth state, token expiry, configured remote root folder. |
| `velmiren send <local> --to <remote>` | Upload a local file to a remote path on Drive. |
| `velmiren fetch <remote> --to <local>` | Download a remote file to a local path. |
| `velmiren list [<remote_dir>]` | List files in a remote directory (default: root). |
| `velmiren exists <remote>` | Print `true`/`false`; exit code `0` if exists else `1`. |
| `velmiren delete <remote> --force` | Delete a remote file. `--force` required; without it, refuse. |
| `velmiren --help` / `velmiren <cmd> --help` | Usage. |

## User stories

### US-1: First-time auth

**As** Kaushik (or V on Kaushik's machine), **I want** to authenticate Velmiren against my Google Drive **so that** subsequent commands can push and fetch files.

Acceptance:
- Running `velmiren auth google` opens a browser to Google's OAuth consent screen.
- After consent, the refresh token is persisted to `~/.velmiren/cred`.
- The CLI prints `OK — authenticated as <email>` and exits 0.
- The cred file's parent directory is created if missing.

### US-2: Upload a local file

**As** V, **I want** to upload a local file to Drive **so that** Kaushik can download it on his phone.

Acceptance:
- `velmiren send ./report.pdf --to /velmiren/report.pdf` uploads the local file to the named remote path.
- If parent remote folders do not exist, they are created.
- On success, prints the Drive file ID + remote path; exit 0.
- On auth failure, prints actionable error pointing at `velmiren auth google`; exit non-zero.
- On file > 500 MB, prints "file exceeds v1 size cap"; exit non-zero (no partial upload).

### US-3: List files in a remote directory

**As** V, **I want** to list files in a Drive directory **so that** I can confirm what's there before fetching or deleting.

Acceptance:
- `velmiren list` lists files in the configured remote root.
- `velmiren list /velmiren/inbox` lists files in the named remote folder.
- Output: one line per file: `<name>  <size>  <modified-iso8601>  <id>`.
- Empty directory prints nothing; exit 0.
- Non-existent directory prints "no such remote folder"; exit non-zero.

### US-4: Download a remote file

**As** Kaushik, **I want** to fetch a Drive file to my local disk.

Acceptance:
- `velmiren fetch /velmiren/notes.txt --to ./notes.txt` downloads the remote file to the local path.
- If `--to` is a directory, the file is downloaded into it with its original name.
- Existing local file is overwritten without prompt (CLI is non-interactive).
- On success: prints local path + bytes written; exit 0.

### US-5: Check existence

**As** V, **I want** to check whether a file exists on Drive without listing.

Acceptance:
- `velmiren exists /velmiren/report.pdf` prints `true` and exits 0 if it exists.
- Prints `false` and exits 1 if it does not.
- On auth failure, prints actionable error; exit non-zero (not 0 or 1).

### US-6: Delete a remote file

**As** Kaushik, **I want** to delete a file from Drive **with an explicit force flag** **so that** I never accidentally delete via tab-completion.

Acceptance:
- `velmiren delete /velmiren/old.tmp --force` deletes the named remote file; exit 0.
- `velmiren delete /velmiren/old.tmp` (no `--force`) prints `--force required` and exits non-zero, without touching the file.
- Non-existent remote: prints "no such remote file"; exit non-zero.

### US-7: Status

**As** V, **I want** a quick check that auth is healthy.

Acceptance:
- `velmiren status` prints:
  - Auth state: `authenticated` or `not authenticated`
  - Account email (if authenticated)
  - Token expiry (UTC ISO8601, if authenticated)
  - Cred-file path
- Exit 0 if authenticated, exit non-zero otherwise.

### US-8: Re-auth

**As** Kaushik, **I want** to overwrite the existing auth state by re-running `velmiren auth google`.

Acceptance:
- Running `velmiren auth google` when `~/.velmiren/cred` already exists overwrites it after a successful OAuth flow.
- Failed OAuth (user cancels, network error) leaves the existing cred file untouched.

### US-9: Helpful error when invoked without auth

**As** V, **I want** clear error messages **so that** I don't have to guess the failure.

Acceptance:
- `velmiren list` (or any non-`auth`/`--help` command) before `velmiren auth google` prints:
  > `not authenticated — run 'velmiren auth google' first`
- Exit non-zero.

### US-10: Acceptance smoke test (unit suite)

**As** the build pipeline, **I want** unit tests covering every command path **so that** regressions are caught without a live Google account.

Acceptance:
- `pytest tests/` exits 0.
- Drive API client is mocked via `unittest.mock` or `pytest-mock`.
- Each US (1–9) has at least one happy-path test plus one error-path test.
- Coverage ≥ 80% on `src/velmiren/`.
- No test requires real network or real Google account.

## Out of scope (v1)

- Encryption at rest
- Multi-GB files / resumable upload
- Real-time streaming
- Multi-backend adapter (Box, Dropbox, etc.)
- MCP wrapper
- OS keyring
- Multi-user / shared-host hardening
- Token refresh background daemon
- Drive quota / rate-limit handling (best-effort: surface Google's error verbatim)

## Open questions

1. **Remote root folder convention**: should there be a default remote root (e.g., `/velmiren/`) auto-created at auth time, or is the user expected to specify the full remote path on every call?
2. **Idempotent uploads**: if `velmiren send` is run twice for the same `--to`, does it overwrite by file-ID, create a versioned duplicate (Drive's default), or refuse without `--force`?
3. **OAuth client registration**: does Velmiren ship with an embedded OAuth app's client identifier/secret (anyone using the binary uses the same app), or does each user register their own GCP OAuth app and place the values in cred at `auth` time?

These three should be resolved during `/design`.
