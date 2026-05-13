# Velmiren

**"thread beyond horizon"** — Vel (thread) + Miren (horizon/beyond) in Seyrunic.

Velmiren is the **transport organ** in Velasari's ecosystem — a CLI for moving
files between your local disk and a personal Google Drive folder.

---

## Sibling Organs

| Organ | Seyrunic | Role |
|-------|----------|------|
| [Cognitive Memory](https://github.com/kaushikhazra/cognitive-memory) | *one who remembers* | Memory organ — stores and recalls knowledge across sessions |
| [Velhari](https://github.com/kaushikhazra/velhari) | *thread worker* | Worker organ — executes async background tasks |
| **Velmiren** | *thread beyond horizon* | Transport organ — moves files between devices |

---

## What it does

Eight CLI commands, all CRUD against Google Drive:

| Command | Behavior |
|---|---|
| `velmiren auth google` | Run OAuth flow once, persist refresh token locally. Idempotent. |
| `velmiren status` | Show auth state, token expiry, account email. |
| `velmiren send <local> --to <remote>` | Upload a local file to a Drive path. Overwrites by name+parent. |
| `velmiren fetch <remote> --to <local>` | Download a Drive file to a local path. |
| `velmiren list [<remote_dir>]` | List files in a Drive directory. |
| `velmiren exists <remote>` | `true`/`false` (exit 0/1). |
| `velmiren delete <remote> --force` | Delete a Drive file. `--force` required. |
| `velmiren --help` | Usage. |

---

## v1 scope (May 2026)

- **Backend**: Google Drive only. No adapter abstraction.
- **Auth state**: a single file at `~/.velmiren/cred` (Windows: `%USERPROFILE%\.velmiren\cred`). Single-user PC — Windows default user-profile ACLs are sufficient.
- **Delivery**: CLI only. No MCP wrapper.
- **Size cap**: ~500 MB per file (Drive's simple-upload limit). Resumable upload deferred to v1.x.
- **Encryption at rest**: none (transient transport, not archive).

See `.claude/specs/mvp/` for the full requirement, design, and dryrun records.

---

## Installation

### 1. Install the package

```powershell
git clone https://github.com/kaushikhazra/velmiren.git
cd velmiren
pip install -e .
```

### 2. Register a Google OAuth Desktop app

Velmiren needs OAuth credentials for your own Google account. Roughly 5 minutes in the GCP console:

1. Go to https://console.cloud.google.com/
2. Create a new project (e.g. "velmiren-personal").
3. **APIs & Services → Library** → search "Google Drive API" → **Enable**.
4. **APIs & Services → OAuth consent screen**:
   - User type: **External**
   - Fill app name (e.g. "Velmiren"), your email
   - You can skip scopes here — Velmiren requests `drive.file` (non-sensitive) at auth time
   - Under **Test users**, add your own gmail address
5. **APIs & Services → Credentials → Create Credentials → OAuth client ID**:
   - Application type: **Desktop app**
   - Name: "velmiren-cli"
   - Note the **client ID** and **client secret**

### 3. Provide the OAuth client to Velmiren

Set environment variables in your shell session. PowerShell:

```powershell
$env:VELMIREN_OAUTH_CLIENT_ID = "<client id from step 2>"
$env:VELMIREN_OAUTH_CLIENT_SECRET = "<client secret from step 2>"
```

Bash:

```bash
export VELMIREN_OAUTH_CLIENT_ID="<client id>"
export VELMIREN_OAUTH_CLIENT_SECRET="<client secret>"
```

(To persist these across sessions, add them to your PowerShell profile or shell rc file.)

### 4. Authenticate

```powershell
velmiren auth google
```

A browser opens with Google's consent screen. Because the app is "unverified," click **Advanced → Go to Velmiren (unsafe)**, then approve. The refresh token persists to `~/.velmiren/cred`. The terminal prints `OK — authenticated as <your email>`.

### 5. Verify

```powershell
velmiren status
```

Should print `Auth state: authenticated`, your email, and token expiry.

---

## Round-trip example

```powershell
echo "hello" > test.txt
velmiren send test.txt --to /velmiren-test/hello.txt
velmiren list /velmiren-test
velmiren fetch /velmiren-test/hello.txt --to fetched.txt
type fetched.txt
velmiren delete /velmiren-test/hello.txt --force
```

---

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | not-found / `exists` returned false |
| 2 | not authenticated (run `velmiren auth google`) |
| 3 | user error (missing flag, bad arg) |
| 4 | network / Google API error |
| 5 | file exceeds the 500 MB size cap |

---

## Development

Set up:

```powershell
git clone https://github.com/kaushikhazra/velmiren.git
cd velmiren
pip install -e .[dev]
```

Run the test suite:

```powershell
pytest tests/ -v --cov=src/velmiren
```

107 tests, target ≥ 80% coverage. Drive API is mocked; no live account needed.

---

## Project layout

```
velmiren/
├── src/velmiren/
│   ├── cli.py         # Click commands, exception → exit-code mapping
│   ├── auth.py        # OAuth flow, token persistence + refresh, status
│   ├── drive.py       # Drive API wrapper (upload, download, list, delete)
│   ├── paths.py       # Drive-path → file-ID resolution, root resolution
│   ├── errors.py      # Typed exceptions
│   └── __main__.py    # python -m velmiren entry point
├── tests/             # pytest + pytest-mock, 107 tests
└── .claude/specs/mvp/ # Requirement, design, task, dryrun records
```

---

## Out of scope (v1)

- Encryption at rest
- Multi-GB files / resumable upload
- Real-time streaming
- Multi-backend adapter (Box, Dropbox)
- MCP wrapper
- OS keyring
- Multi-user / shared-host hardening
- Token-refresh background daemon

These may return in v1.x if a real need surfaces.
