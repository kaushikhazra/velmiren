# Velmiren

**"thread beyond horizon"** — Vel (thread) + Miren (horizon/beyond) in Seyrunic.

Velmiren is the **transport organ** in Velasari's ecosystem — a CLI for secure,
bi-directional file transport between Velasari's PC and Kaushik's devices.

---

## Sibling Organs

| Organ | Seyrunic | Role |
|-------|----------|------|
| [Cognitive Memory](https://github.com/kaushik/cognitive-memory) | *one who remembers* | Memory organ — stores and recalls knowledge across sessions |
| [Velhari](https://github.com/kaushik/velhari) | *thread worker* | Worker organ — executes async background tasks |
| **Velmiren** | *thread beyond horizon* | Transport organ — moves files securely between devices |

---

## Architecture

Velmiren is built on an **adapter pattern** — the core CLI and transport logic are
backend-agnostic. Concrete backends implement a `TransportBackend` interface, making
it straightforward to add new providers without touching core logic.

```
velmiren/
├── cli.py          # Click-based CLI entry point
├── core.py         # Transport orchestration (backend-agnostic)
├── backends/
│   ├── base.py     # TransportBackend abstract interface
│   ├── gdrive.py   # Google Drive backend (v1)
│   └── ...         # Box, Dropbox, etc. (future)
└── credentials.py  # Keyring-based OS-native credential management
```

### v1 Backend: Google Drive

- Uses the Google Drive API v3 via `google-api-python-client`
- OAuth2 flow handled by `google-auth-oauthlib`
- Credentials stored in the OS native keyring via `keyring` (no plaintext secrets)

### Future Backends (adapter slots ready)

- Box
- Dropbox
- SFTP / SCP
- S3-compatible

---

## Credential Strategy

Velmiren uses **OS-native keyring storage** (`keyring` library) — no credentials
are written to disk in plaintext. On Windows this is Windows Credential Manager,
on macOS it is Keychain, on Linux it falls back to the Secret Service API.

---

## CLI Usage (planned)

```bash
# Upload a file to the configured backend
velmiren push ./report.pdf

# Download a file by name or path
velmiren pull report.pdf ./local/

# List files in the remote transport directory
velmiren ls

# Configure credentials for a backend
velmiren auth gdrive

# Show current configuration
velmiren config show
```

---

## Development Status

**Spec phase.** No implementation code exists yet.

Spec documents live in `.claude/specs/mvp/`:
- `requirement.md` — user stories and acceptance criteria
- `design.md` — architecture decisions and data models
- `task.md` — implementation checklist

See the Taskyn project board for current status.
