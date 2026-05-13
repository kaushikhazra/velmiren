# Design Dry-Run Report #2

**Document**: `.claude/specs/mvp/design.md` (v1.1)
**Requirement**: `.claude/specs/mvp/requirement.md`
**Reviewed**: 2026-05-13
**Prior**: dryrun-design-1.md — PASS WITH WARNINGS (1C/3W); all 4 remediated in v1.1.

---

## Pass-1 Remediation Verification

### C-1 (account email) — PASS

- **Schema (§2)**: now lists exactly six fields; email is the sixth, described as "fetched from Google's userinfo endpoint immediately after the OAuth token exchange and persisted here so that `velmiren status` can display it without a live network call." Six-field count is explicit.
- **OAuth scope (§3)**: `SCOPES` list is `["https://www.googleapis.com/auth/drive.file", "openid", "email"]`. §2 scope field mirrors this as `drive.file openid email`. Consistent.
- **Userinfo fetch (§3)**: `_fetch_email(user_cred)` is specified — `GET https://openidconnect.googleapis.com/v1/userinfo` with Bearer header, extracts `email` field. Called immediately after `flow.run_local_server()` returns, result passed to `_serialize_cred`.
- **US-1 AC3 trace**: `run_oauth_flow` → `_fetch_email` → `_serialize_cred` (6 fields) → `_atomic_write_cred` → cli.py prints `OK — authenticated as <email>`. Complete.
- **US-7 AC2 trace**: email persisted in cred file → `status` command reads it from loaded cred data → prints. No extra network call. Complete.
- **§8 fixture**: `fake_cred_data` description updated to reference six fields matching §2 (including email). ✓
- **§10 Files Changed**: `auth.py` row includes `_fetch_email()` with description. ✓

### W-1 (paths.py service vs cred) — PASS

- **§1**: "paths.py receives the Drive service object from drive.py rather than constructing its own — keeping service-lifecycle ownership in drive.py." ✓
- **§5 signatures**: `resolve(svc, remote_path)`, `ensure_path(svc, remote_path)` — first parameter is `svc` throughout. ✓
- **§4 call sites**: `paths.ensure_path(svc, remote_path)` in `upload()`, `paths.resolve(svc, remote_path)` in `download()` and `delete_file()`. All pass `svc` (constructed by `_service(cred)` at the top of each drive.py function). ✓
- **No circular import**: `drive.py` → `paths.py` (one-way); `paths.py` never imports `drive`. ✓

### W-2 (HttpError wrapping) — PASS

- **§4 new subsection "HttpError wrapping"**: every public `drive.py` function wraps `.execute()` calls in try/except catching `googleapiclient.errors.HttpError`, re-raises as `NetworkError(str(e), status_code=e.resp.status)`. Code sample provided. ✓
- **§7 `NetworkError`**: class comment confirms optional `status_code` kwarg. ✓
- **End-to-end mapping**: `HttpError` → `NetworkError` (exit_code=4) → `_run` catches `VelmirenError` → `sys.exit(4)`. The design explicitly states "no change to `_run` is required." Complete chain. ✓

### W-3 (VELMIREN_REMOTE_ROOT) — PASS

- **§5 `_resolve_remote_root()`**: fully specified module-level helper in `paths.py`. ✓
- **Step 1**: reads `VELMIREN_REMOTE_ROOT` env var. If set: plain folder name replaces `"velmiren"` as first segment under root; `id:` prefix → strip prefix, use remainder as `parent_id` directly. Explicit prefix convention adopted (per O-2 recommendation from pass 1). ✓
- **Step 2**: falls back to `"velmiren"` if env var is not set. ✓
- **Integration**: called at start of both `_walk()` and `ensure_path()` in place of hardcoded `parent_id = "root"`. When value is a folder name, a name query under Drive's `root` pseudo-ID obtains the actual `parent_id`. ✓
- **§10 Files Changed**: `paths.py` row includes `_resolve_remote_root()`. ✓

---

## Full 8-Pass Review (checking for new issues)

### Pass 1: Completeness Check

All user stories US-1 through US-10 traced to design elements. No orphan requirements. No scope creep (Future Work section clearly delineated). Email gap from pass 1 is closed. No new gaps.

### Pass 2: Data Flow Trace

- **Email**: userinfo endpoint → `_fetch_email` → `_serialize_cred` → cred file (write) → `_read_cred_file` → `status` display. Complete loop.
- **Remote root**: env var → `_resolve_remote_root()` → seed `parent_id` for `_walk()` / `ensure_path()`. Complete.
- **HttpError status code**: `e.resp.status` → `NetworkError.status_code` → available for logging (not currently displayed, but stored). Acceptable — no dangling data.
- **All other data flows** (token lifecycle, file upload/download, path resolution, cache) unchanged from v1.0 and were clean in pass 1.

No new data-flow issues.

### Pass 3: Interface Contract Validation

- `drive.py` ↔ `paths.py`: `svc` object passed consistently. ✓
- `drive.py` ↔ `errors.py`: `HttpError` → `NetworkError` with status_code. ✓
- `auth.py` ↔ `cli.py`: `load()` returns cred object; `run_oauth_flow()` returns dict. ✓
- `cli.py` ↔ `errors.py`: `_run` catches `VelmirenError`, reads `.exit_code` and `.message`. ✓

No new contract issues.

### Pass 4: State Machine & Transitions

Auth states (unauthenticated → authenticated → expired → re-authenticated) unchanged. Atomic write ensures no partial-state cred files. No new stateful components introduced.

### Pass 5: Failure Path Analysis

- **`_fetch_email` failure**: if the userinfo call fails after a successful OAuth exchange (network drops in the ~100ms window), the exception propagates up through `run_oauth_flow`, preventing `_atomic_write_cred` from executing. The temp file is cleaned up by the except clause in `_atomic_write_cred` (if it was reached) or never created. Existing cred file (if any) is untouched — satisfying US-8 AC2. The user sees a traceback and can re-run `auth google`. Acceptable for v1; the window is vanishingly small and the failure mode is safe.
- **HttpError wrapping**: now covers all five public `drive.py` functions. Exit code 4 is reached. ✓

No new failure-path gaps.

### Pass 6: Concurrency & Ordering

No changes affect concurrency. Single-user CLI, single-process. TOCTOU in upload noted in pass 1 O-4 — still a non-issue for v1.

### Pass 7: Edge Cases & Boundaries

- **`VELMIREN_REMOTE_ROOT` set to empty string**: the design says "if it is set, its value is returned." An empty string would produce an empty first segment, causing the walk to fail with `RemoteNotFoundError`. Unlikely user action and produces a safe (if opaque) error. Not worth a warning for v1.
- **`id:` prefix with invalid ID**: user sets `VELMIREN_REMOTE_ROOT=id:garbage`. The walk uses `garbage` as `parent_id`; the first Drive query returns zero results → `RemoteNotFoundError`. Safe failure. ✓

No new edge-case issues.

### Pass 8: Task Spec Alignment

`task.md` contains only the header — no tasks to validate. Task spec will be populated during `/implement`. No alignment issues.

---

## Observations (worth noting, no action required)

### [O-1] §6 OQ-1 still describes the old character-class heuristic

§6 OQ-1 resolution text says: "If set to a raw Drive file ID (recognisable as a 28–44 character alphanumeric string with no `/`), it is used directly as the root parent ID." However, §5 `_resolve_remote_root()` specifies the `id:` prefix convention instead, explicitly stating it is "preferred over a length/character-class heuristic to eliminate false positives." §10 Files Changed also references the `id:` prefix. The §5 spec governs implementation, so no implementor confusion is expected — but §6's stale prose is a minor inconsistency.

### [O-2] §8 `fake_cred_data` description has a five/six count stutter

§8 first describes `fake_cred_data` as "a plain dict with all five cred-file field names" then immediately says "The field names in the dict match the six names described in §2 (including the email field)." The second sentence is correct (six fields). The first sentence carries over from v1.0. Cosmetic only — the intent is unambiguous.

---

## AC Traceability Table

| AC | User Story | Design Location | Status |
|----|-----------|----------------|--------|
| US-1 AC1: Opens browser to OAuth consent | US-1 | §3 `InstalledAppFlow.run_local_server(open_browser=True)` | Covered |
| US-1 AC2: Refresh token persisted to cred file | US-1 | §2 schema (6 fields) + §3 `_atomic_write_cred` | Covered |
| US-1 AC3: Prints `OK — authenticated as <email>` | US-1 | §3 `_fetch_email` → §7 AC-string table | Covered |
| US-1 AC4: Parent directory created if missing | US-1 | §3 `cred_path.parent.mkdir(parents=True, exist_ok=True)` | Covered |
| US-2 AC1: Upload to named remote path | US-2 | §4 `upload()` | Covered |
| US-2 AC2: Parent remote folders created | US-2 | §5 `ensure_path` + `_get_or_create_folder` | Covered |
| US-2 AC3: Prints Drive file ID + remote path | US-2 | §4 `upload()` returns file ID; cli.py prints | Covered |
| US-2 AC4: Auth failure → actionable error | US-2 | §7 `NotAuthenticatedError` (exit 2) | Covered |
| US-2 AC5: File > 500 MB → size cap error | US-2 | §4 `upload()` size check → `SizeCapError` (exit 5) | Covered |
| US-3 AC1: `list` shows remote root | US-3 | §4 `list_dir` + §5 `_resolve_remote_root` | Covered |
| US-3 AC2: `list <path>` shows named folder | US-3 | §4 `list_dir` + §5 `resolve` | Covered |
| US-3 AC3: Output format per-line | US-3 | §4 `list_dir` returns `name, size, modifiedTime, id` | Covered |
| US-3 AC4: Empty directory → exit 0 | US-3 | §4 "Empty result is valid (exit 0, no output)" | Covered |
| US-3 AC5: Non-existent dir → error | US-3 | §7 `RemoteNotFoundError` ("no such remote folder", exit 1) | Covered |
| US-4 AC1: Download remote file | US-4 | §4 `download()` | Covered |
| US-4 AC2: `--to` directory → original name | US-4 | §4 `download()` `if dest.is_dir()` branch | Covered |
| US-4 AC3: Overwrites existing local file | US-4 | §4 `dest.open("wb")` | Covered |
| US-4 AC4: Prints local path + bytes written | US-4 | §4 `download()` returns `dest.stat().st_size` | Covered |
| US-5 AC1: `true`, exit 0 | US-5 | §7 AC-string table | Covered |
| US-5 AC2: `false`, exit 1 | US-5 | §7 AC-string table | Covered |
| US-5 AC3: Auth failure → exit non-zero (not 0/1) | US-5 | §7 `NotAuthenticatedError` exit 2 | Covered |
| US-6 AC1: Delete with `--force`, exit 0 | US-6 | §4 `delete_file()` | Covered |
| US-6 AC2: No `--force` → error | US-6 | §7 `UserError` ("--force required", exit 3) | Covered |
| US-6 AC3: Non-existent → error | US-6 | §7 `RemoteNotFoundError` ("no such remote file", exit 1) | Covered |
| US-7 AC1: Auth state display | US-7 | §3 `auth.load()` success/failure | Covered |
| US-7 AC2: Account email | US-7 | §2 email field + §3 `_fetch_email` + cli.py reads from cred data | Covered |
| US-7 AC3: Token expiry (UTC ISO8601) | US-7 | §3 `auth.load()` → `cred.expiry` | Covered |
| US-7 AC4: Cred-file path | US-7 | §3 `_cred_path()` | Covered |
| US-7 AC5: Exit 0 if auth, non-zero otherwise | US-7 | §7 exit-code table | Covered |
| US-8 AC1: Re-auth overwrites on success | US-8 | §3 `_atomic_write_cred` | Covered |
| US-8 AC2: Failed OAuth leaves cred untouched | US-8 | §3 atomic-write temp-file pattern | Covered |
| US-9 AC1: `not authenticated` message | US-9 | §7 `NotAuthenticatedError.message` | Covered |
| US-9 AC2: Exit non-zero | US-9 | §7 exit 2 | Covered |
| US-10 AC1: `pytest tests/` exits 0 | US-10 | §8 framework section | Covered |
| US-10 AC2: Drive API mocked | US-10 | §8 mock-points table | Covered |
| US-10 AC3: Each US happy + error path | US-10 | §8 coverage-per-US table | Covered |
| US-10 AC4: Coverage >= 80% | US-10 | §8 `--cov-fail-under=80` | Covered |
| US-10 AC5: No real network | US-10 | §8 "No test requires a real network connection" | Covered |

---

## Files Changed Traceability

| File | Design Section | Implementable? |
|------|---------------|----------------|
| `src/velmiren/__init__.py` | §1 | Yes |
| `src/velmiren/__main__.py` | §1 | Yes |
| `src/velmiren/errors.py` | §7 | Yes |
| `src/velmiren/auth.py` | §3 (incl. `_fetch_email`) | Yes |
| `src/velmiren/paths.py` | §5 (incl. `_resolve_remote_root`) | Yes |
| `src/velmiren/drive.py` | §4 (incl. HttpError wrapping) | Yes |
| `src/velmiren/cli.py` | §1 + §7 | Yes |
| `pyproject.toml` | §9 | Yes |
| `tests/__init__.py` | §8 | Yes |
| `tests/conftest.py` | §8 (6-field `fake_cred_data`) | Yes |
| `tests/test_errors.py` | §8 | Yes |
| `tests/test_auth.py` | §8 | Yes |
| `tests/test_paths.py` | §8 | Yes |
| `tests/test_drive.py` | §8 | Yes |
| `tests/test_cli.py` | §8 | Yes |

All 15 files implementable from design alone. No pending gaps.

---

## Summary

| Critical | Warnings | Observations |
|----------|----------|--------------|
| 0        | 0        | 2            |

**Verdict: PASS (0C / 0W)**

All four issues from pass 1 (C-1, W-1, W-2, W-3) are fully remediated. No new critical gaps or warnings introduced by the remediations. Two cosmetic observations noted (stale §6 heuristic prose, §8 five/six stutter) — neither affects implementability. Design is ready for `/implement`.
