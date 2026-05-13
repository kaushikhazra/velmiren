# Design Dry-Run Report #1

**Document**: `.claude/specs/mvp/design.md`
**Requirement**: `.claude/specs/mvp/requirement.md`
**Reviewed**: 2026-05-13

---

## Verdict

**PASS WITH WARNINGS (1C / 3W)**

| Critical | Warnings | Observations |
|----------|----------|--------------|
| 1        | 3        | 4            |

---

## Critical Gaps (must fix before implementation)

### [C-1] Account email is referenced but never sourced or stored

- **Pass**: Pass 1 (Completeness) + Pass 2 (Data Flow)
- **What**: US-1 AC3 requires printing `OK — authenticated as <email>` after auth. US-7 AC2 requires displaying "Account email (if authenticated)" in status output. The design's auth-state schema (§2) defines exactly five stored fields — refresh token, client identifier, client secret, token endpoint URI, scope. None is an email address. No section of the design specifies how or when the email is obtained (userinfo endpoint call, ID-token parsing, or any other mechanism). The `run_oauth_flow` return dict and `_serialize_cred` function are defined as extracting the five stored fields only.
- **Risk**: An implementor cannot satisfy US-1 AC3 or US-7 AC2 from the design alone. They must invent a mechanism — each option (6th cred field, live userinfo call, ID-token parse) has different implications for the cred-file schema, network behaviour on `status`, and test fixtures.
- **Fix**: Specify the email source. Recommended: after `flow.run_local_server()` completes, call the Google userinfo endpoint (`GET https://www.googleapis.com/oauth2/v1/userinfo`) using the freshly minted access token, extract the `email` field, and store it as a 6th field in the cred file. This keeps `status` offline (no extra network call) and aligns with the existing "five fields stored" pattern (now six). Update §2 (schema), §3 (`_serialize_cred`), and §8 (`fake_cred_data` fixture) accordingly.

---

## Warnings (should fix, may cause issues)

### [W-1] `paths.py` service-object contract contradicts its own function signatures

- **Pass**: Pass 3 (Interface Contract Validation)
- **What**: §1 (Module Layout) states: "`paths.py` receives the Drive service object from `drive.py` rather than constructing its own — keeping service-lifecycle ownership in `drive.py`." However, every call site in §4 (`drive.py`) passes `cred` — not a service object — to `paths.py`:
  - `paths.ensure_path(cred, remote_path)` in `upload()`
  - `paths.resolve(cred, remote_path)` in `download()`, `delete_file()`
  
  The §5 function signatures confirm: `resolve(cred, remote_path)` and `ensure_path(cred, remote_path)`. If `paths.py` takes `cred` and internally constructs its own service via `drive._service(cred)`, that creates a circular import (`drive` → `paths` → `drive`). If `paths.py` is meant to receive a pre-built service object, then all §4 and §5 code snippets show the wrong parameter.
- **Risk**: Implementor must resolve the contradiction. If they guess wrong, they introduce either a circular import or a second service-construction call site that contradicts §1's ownership rule.
- **Suggestion**: Pick one. Cleanest option: change `paths.py` public signatures to accept a service object (not `cred`), and have `drive.py` pass `svc` after constructing it. Update §4 call sites and §5 signatures to match. This preserves §1's stated ownership rule.

### [W-2] Google API `HttpError` exceptions are never caught or wrapped

- **Pass**: Pass 5 (Failure Path Analysis)
- **What**: The error model (§7) defines `NetworkError` with exit code 4 for "Network error or Google API error (non-auth)." The requirement's out-of-scope section says "surface Google's error verbatim." However, no `drive.py` function shows a try/except around Drive API calls (`svc.files().list().execute()`, `svc.files().create().execute()`, etc.). The `_run` wrapper in `cli.py` catches `VelmirenError` only. A `googleapiclient.errors.HttpError` (e.g., 403 quota exceeded, 500 internal server error) would propagate uncaught, producing a raw Python traceback instead of a clean error message with exit code 4.
- **Risk**: Any Drive API error that isn't an auth error produces an ugly traceback instead of the designed clean error output. This affects every command except `auth google`.
- **Suggestion**: Add a try/except in `_run` (or a decorator on each `drive.py` public function) that catches `googleapiclient.errors.HttpError`, extracts the error message, and raises `NetworkError(str(e))`. Alternatively, add `except Exception` as a final catch in `_run` that wraps unexpected errors into a `NetworkError`. Specify which approach in the design.

### [W-3] `VELMIREN_REMOTE_ROOT` env-var integration point is unspecified

- **Pass**: Pass 2 (Data Flow) + Pass 7 (Edge Cases)
- **What**: §6 OQ-1 describes the behaviour of the `VELMIREN_REMOTE_ROOT` env var in detail — plain folder name replaces `"velmiren"` as the first segment; raw Drive file ID (28-44 char alphanumeric) is used directly as the root parent ID. However, the `paths.py` code in §5 hardcodes `parent_id = "root"` at the start of both `resolve` and `ensure_path`. No code, pseudocode, or narrative specifies WHERE in `paths.py` the env var is read, HOW the format heuristic is applied, or HOW the result modifies the walk's starting `parent_id`.
- **Risk**: Implementor must invent the integration. The format heuristic (§10 OQ-2 self-flags this) could misclassify folder names that happen to be 28-44 alphanumeric characters.
- **Suggestion**: Add a `_resolve_root()` helper in `paths.py` that reads `VELMIREN_REMOTE_ROOT`, applies the heuristic, and returns the starting `parent_id`. Show it in §5 and call it at the top of `_walk`. Consider adopting the explicit `id:<file_id>` prefix format (as §10 OQ-2 suggests) instead of the length/character-class heuristic.

---

## Observations (worth discussing)

### [O-1] `velmiren status` triggers a live token refresh (design-flagged)

The design's §10 OQ-1 honestly flags that `status` must call `auth.load()`, which performs a network token-refresh as a side effect, to populate `cred.expiry`. This means `status` requires network access and cannot be run offline. For a v1 single-user CLI this is an acceptable tradeoff — the alternative (storing access-token expiry in the cred file) adds staleness complexity. Worth confirming with Kaushik that `status` requiring connectivity is fine.

### [O-2] `VELMIREN_REMOTE_ROOT` format heuristic could be replaced with explicit prefix

The design's §10 OQ-2 flags the ambiguity of the format heuristic. An explicit `id:<file_id>` convention is strictly better — zero false positives, self-documenting in env-var config. Recommend adopting this if the env-var feature ships in v1.

### [O-3] `velmiren list` root-resolution ownership is unfixed (design-flagged)

The design's §10 OQ-3 notes that `cli.py` needs to resolve the remote root folder ID for `velmiren list` (no argument), and it's unclear whether this lives in `paths.py` (via `resolve(cred, "/velmiren")` or a new `get_root_id`) or inline in `cli.py`. Either works; recommend a `paths.root_folder_id(cred)` helper so the root-resolution logic (including env-var override) has a single home.

### [O-4] Idempotent upload has a TOCTOU window

`_find_by_name` + conditional `create`/`update` in `upload()` is not atomic. Two concurrent `send` commands to the same `--to` path could both see "not found" and both create, producing a duplicate. For a single-user CLI tool this is a non-issue. Noting for completeness only.

---

## AC Traceability Table

| AC | User Story | Design Location | Status |
|----|-----------|----------------|--------|
| US-1 AC1: Opens browser to OAuth consent | US-1 | §3 `InstalledAppFlow.run_local_server(open_browser=True)` | Covered |
| US-1 AC2: Refresh token persisted to cred file | US-1 | §2 schema + §3 `_atomic_write_cred` | Covered |
| US-1 AC3: Prints `OK — authenticated as <email>` | US-1 | §7 AC-string table (string mapped) | **Gap** — email source unspecified → [C-1] |
| US-1 AC4: Parent directory created if missing | US-1 | §3 `cred_path.parent.mkdir(parents=True, exist_ok=True)` | Covered |
| US-2 AC1: Upload to named remote path | US-2 | §4 `upload()` | Covered |
| US-2 AC2: Parent remote folders created | US-2 | §5 `ensure_path` + `_get_or_create_folder` | Covered |
| US-2 AC3: Prints Drive file ID + remote path | US-2 | §4 `upload()` returns file ID; cli.py prints | Covered |
| US-2 AC4: Auth failure → actionable error | US-2 | §7 `NotAuthenticatedError` (exit 2) | Covered |
| US-2 AC5: File > 500 MB → size cap error | US-2 | §4 `upload()` size check → `SizeCapError` (exit 5) | Covered |
| US-3 AC1: `list` shows remote root | US-3 | §4 `list_dir` + §6 OQ-1 remote root | Covered |
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
| US-7 AC2: Account email | US-7 | — | **Gap** → [C-1] |
| US-7 AC3: Token expiry (UTC ISO8601) | US-7 | §10 OQ-1 (via `cred.expiry` after refresh) | Covered (side-effect noted in [O-1]) |
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

## Files Changed Traceability Table

| File | Design Section | Implementable from Design? |
|------|---------------|---------------------------|
| `src/velmiren/__init__.py` | §1 (module layout) | Yes — add `__version__` only |
| `src/velmiren/__main__.py` | §1 (module layout) | Yes — 2-line entry point |
| `src/velmiren/errors.py` | §7 (complete hierarchy + exit codes + string catalogue) | Yes |
| `src/velmiren/auth.py` | §3 (full flow, code samples, helper descriptions) | Yes — pending [C-1] email fix |
| `src/velmiren/paths.py` | §5 (walk algorithm, cache, ensure_path, code samples) | Yes — pending [W-1] contract fix, [W-3] env-var integration |
| `src/velmiren/drive.py` | §4 (all functions, API mapping, code samples) | Yes — pending [W-2] error wrapping |
| `src/velmiren/cli.py` | §1 + §7 (commands listed, `_run` wrapper, AC-string→exit-code table) | Yes — thin orchestration; all underlying functions fully specified |
| `pyproject.toml` | §9 (exact dependency lines + versions) | Yes |
| `tests/__init__.py` | §8 | Yes — empty marker |
| `tests/conftest.py` | §8 (fixture code samples) | Yes — pending [C-1] for `fake_cred_data` update |
| `tests/test_errors.py` | §8 (implied by hierarchy) | Yes |
| `tests/test_auth.py` | §8 (US mapping + mock-points table) | Yes |
| `tests/test_paths.py` | §8 (US mapping) | Yes |
| `tests/test_drive.py` | §8 (US mapping + mock-points table) | Yes |
| `tests/test_cli.py` | §8 (US mapping + mock-points table) | Yes |

---

## Open-Question Resolution Review

| OQ | Topic | Resolved In | Recommendation | Rationale | Rejected Alt | Verdict |
|----|-------|-------------|---------------|-----------|--------------|---------|
| OQ-1 | Remote root folder convention | §6 | Default `velmiren` folder under My Drive; `VELMIREN_REMOTE_ROOT` env-var override | Zero-config for `pip install` → `auth` → `send`; folder name not ID avoids re-create issues | Require full absolute paths every call | **OK** — clear, well-reasoned |
| OQ-2 | Idempotent uploads | §6 | Lookup by name + parent; PATCH existing, else create | Matches `cp`/`scp` mental model; avoids Drive clutter | Drive default version-on-duplicate | **OK** — clear, well-reasoned |
| OQ-3 | OAuth client registration | §6 | Embedded client ID/secret in `auth.py`; env-var override | Installed-app secret is public per Google docs; `rclone` precedent; zero GCP setup | Each user registers own GCP OAuth app | **OK** — clear, well-reasoned, cites precedent |

---

## Locked-Decision Compliance

| # | Locked Decision | Compliant? | Notes |
|---|----------------|-----------|-------|
| 1 | Google Drive only | Yes | No adapter pattern; `drive.py` calls Drive v3 directly |
| 2 | Auth state in single file at `~/.velmiren/cred` | Yes | §2 schema, §3 read/write |
| 3 | No OS keyring | Yes | §9 explicitly excludes `keyring` |
| 4 | No `chmod` hardening | Yes | Not mentioned anywhere |
| 5 | CLI only, no MCP | Yes | No MCP references in design |
| 6 | No encryption at rest | Yes | Not mentioned |
| 7 | 500 MB per-file cap | Yes | §4 `upload()` enforces |
| 8 | Unit tests with mocked Drive | Yes | §8, no live tests |

---

## Summary

The design is well-structured and thorough. The six-module layout, error hierarchy, and Drive API mapping are clearly specified with implementable code samples. All three open questions from the requirement are resolved with strong rationale and rejected alternatives.

The single critical gap — account email is required by two user stories but absent from the data model and flow — is straightforward to fix (add a userinfo call post-OAuth, store email as a 6th cred-file field). The three warnings are interface-level clarifications that prevent implementor guesswork.

**Verdict: PASS WITH WARNINGS (1C / 3W)**
