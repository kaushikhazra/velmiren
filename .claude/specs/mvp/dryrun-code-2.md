# Code Dry-Run Report #2

**Scope**: `src/velmiren/` (6 modules: errors, auth, drive, paths, cli, __main__)
**Design**: `.claude/specs/mvp/design.md` v1.1
**Prior**: dryrun-code-1.md — PASS WITH WARNINGS (1B / 3W)
**Reviewed**: 2026-05-13

---

## Pass-1 Finding Verification

### [B1] `auth_google` with invalid provider should exit code 3

- **Status**: PASS
- **Location**: `src/velmiren/cli.py`:54-56 — provider check is now inside `_body()`, within the `_run` wrapper.
- **Smoke test**: `python -m velmiren auth foobar` prints `unsupported provider: foobar` and exits 3.
- **Unit test**: `test_cli.py`:74-76 — `test_unknown_provider_exits_three` asserts `result.exit_code == 3` (tightened from `!= 0`).

### [W1] `list` root-resolution should use public API, not private internals

- **Status**: PASS
- **Location**: `src/velmiren/cli.py`:130 — `folder_id = paths.resolve_root_id(svc)` calls the public helper.
- **Public helper**: `src/velmiren/paths.py`:44-61 — `resolve_root_id(svc)` encapsulates `_resolve_remote_root()` + `_lookup_child()` lookup. No private API leakage from `cli.py`.

### [W2] `requests` should be a declared dependency

- **Status**: PASS (confirmed false alarm in pass 1)
- **Location**: `pyproject.toml` — `"requests>=2.31"` is listed in `[project.dependencies]`.
- **Note**: Pass 1 stated it was missing; the dependency was present at implementation time. No code change was needed.

### [W3] File names with apostrophes must be escaped in Drive query strings

- **Status**: PASS
- **Locations**:
  - `src/velmiren/paths.py`:81 — `safe_name = name.replace("'", "\\'")`
  - `src/velmiren/drive.py`:42 — `safe_name = name.replace("'", "\\'")`
- **Unit test**: `tests/test_drive.py`:46-55 — `test_apostrophe_in_name_is_escaped` verifies that querying for `"can't.txt"` produces `"can\\'t.txt"` in the Drive query string.

**Verdict on pass-1 findings**: All 4 items (1B + 3W) are closed.

---

## Pass 2 — Full Code Review

### Pass 1: Design Conformance

| Design element | Status | Notes |
|---|---|---|
| 6-module layout | PASS | All present under `src/velmiren/` |
| Auth state: 6 fields including email | PASS | `_serialize_cred` returns all 6 fields |
| OAuth scope includes `openid email` | PASS | `SCOPES` list at auth.py:22 |
| `_fetch_email` calls userinfo endpoint | PASS | auth.py:136-141 |
| paths.py functions take `svc`, not `cred` | PASS | `resolve(svc, ...)`, `ensure_path(svc, ...)` |
| `_resolve_remote_root` with `id:` prefix convention | PASS | paths.py:28-41 |
| `resolve_root_id(svc)` public helper for root resolution | PASS | paths.py:44-61 |
| drive.py wraps `HttpError` to `NetworkError(status_code=...)` | PASS | All 5 public functions |
| cli.py exit codes per design section 7 | PASS | 0/1/2/3/4/5 all mapped correctly |
| Exception hierarchy: 6 subclasses of `VelmirenError` | PASS | All present in errors.py |
| `_atomic_write_cred` temp-file-then-replace pattern | PASS | auth.py:73-83 |
| `_build_credential` via dynamic import | PASS | auth.py:107-116 |
| Upload idempotent: lookup-then-update-or-create | PASS | drive.py:56-86 |
| Download: dir-target infers remote name | PASS | drive.py:100-102 |
| Per-session path cache | PASS | paths.py:20, resolve() at line 152 |
| `ensure_path` creates missing folders | PASS | paths.py:161-181 |
| `_run` error handler catches `VelmirenError` | PASS | cli.py:26-32 |
| All commands route exceptions through `_run` | PASS | No exception bypass paths remain |

### Pass 2: Execution Path Trace

Traced all 8 commands through `_run` → `_body()` → module calls. Every `VelmirenError` subclass raised inside `_body()` is caught by `_run`. No exception can bypass the handler.

### Pass 3: Error Handling

- `auth foobar` → `UserError` inside `_body()` → `_run` catches → exit 3. PASS.
- `list` with no arg → `resolve_root_id(svc)` → `RemoteNotFoundError` if missing → exit 1. PASS.
- `status` without cred → `NotAuthenticatedError` → exit 2. PASS.
- `delete` without `--force` → `UserError("--force required")` → exit 3. PASS.
- `send` file > 500 MB → `SizeCapError` → exit 5. PASS.

### Pass 4: Input Validation

- Apostrophe escaping in both query-building sites (`paths._lookup_child`, `drive._find_by_name`). PASS.
- File size check before upload. PASS.
- `--force` flag required for delete. PASS.

### Pass 5: Contract Violations

- `requests>=2.31` declared in `pyproject.toml`. PASS.
- All external library imports are from declared dependencies. PASS.

### Pass 6: Concurrency / State

- Module-level `_cache` in paths.py is process-scoped (one CLI invocation). No cross-process corruption risk. PASS.

### Pass 7: Code Quality

- No private API leakage from `cli.py` into `paths.py` internals. PASS.
- `_run` wrapper is used consistently by all 8 commands. PASS.

---

## Bugs

None.

---

## Gaps

None.

---

## Warnings

None.

---

## Style (carried from pass 1, not blocking)

### [S1] Dead function `_is_drive_id` in paths.py

- **File**: `src/velmiren/paths.py`:64-71
- **What**: Unused at any call site; no test covers it. Recommend removing or adding a test in a future cleanup pass.

### [S2] Dead function `is_authenticated` in auth.py

- **File**: `src/velmiren/auth.py`:191-196
- **What**: Never called in production code (`cli.py` uses `auth.get_status()` instead). Recommend removing or adding a test in a future cleanup pass.

---

## AC Trace Table

| US | AC summary | Test(s) | Verdict |
|---|---|---|---|
| US-1 | OAuth flow, cred persisted, prints "OK as email" | `test_auth::TestRunOAuthFlow::test_happy_path_returns_cred_dict`, `test_cli::TestAuthCommand::test_happy_path_prints_ok` | PASS |
| US-1 | Parent dir created if missing | `test_auth::TestAtomicWriteCred::test_creates_parent_dir` | PASS |
| US-1 | Unsupported provider: exit 3 | `test_cli::TestAuthCommand::test_unknown_provider_exits_three` | PASS |
| US-2 | Upload creates/overwrites, returns file ID | `test_drive::TestUpload::test_create_new_file`, `test_update_existing_file` | PASS |
| US-2 | File > 500 MB rejected | `test_drive::TestUpload::test_size_cap_raises`, `test_cli::TestSendCommand::test_size_cap_exits_five` | PASS |
| US-2 | Parent folders created | `test_paths::TestEnsurePath::test_creates_missing_folder`, `test_deep_path_creates_all_folders` | PASS |
| US-3 | List files one-per-line | `test_cli::TestListCommand::test_happy_path_lists_files` | PASS |
| US-3 | Empty dir: exit 0 | `test_cli::TestListCommand::test_empty_folder_exits_zero` | PASS |
| US-3 | Non-existent dir: exit 1 | `test_cli::TestListCommand::test_nonexistent_folder_exits_one` | PASS |
| US-4 | Download to file | `test_drive::TestDownload::test_downloads_to_file`, `test_cli::TestFetchCommand::test_happy_path_prints_bytes` | PASS |
| US-4 | --to is dir: use remote name | `test_drive::TestDownload::test_dir_target_uses_remote_name` | PASS |
| US-5 | true/exit 0 | `test_cli::TestExistsCommand::test_prints_true_exits_zero` | PASS |
| US-5 | false/exit 1 | `test_cli::TestExistsCommand::test_prints_false_exits_one` | PASS |
| US-5 | Auth failure: exit 2 | `test_cli::TestExistsCommand::test_auth_failure_exits_two` | PASS |
| US-6 | Delete with --force: exit 0 | `test_cli::TestDeleteCommand::test_happy_path_exits_zero` | PASS |
| US-6 | No --force: "--force required", exit 3 | `test_cli::TestDeleteCommand::test_no_force_exits_three` | PASS |
| US-6 | Not found: exit 1 | `test_cli::TestDeleteCommand::test_not_found_exits_one` | PASS |
| US-7 | Status authenticated: email + expiry + cred path | `test_cli::TestStatusCommand::test_authenticated_exits_zero` | PASS |
| US-7 | Status not authenticated: exit 2 | `test_cli::TestStatusCommand::test_not_authenticated_exits_nonzero` | PASS |
| US-8 | Re-auth overwrites; failed OAuth leaves original | `test_auth::TestReAuth::test_failed_flow_leaves_original_cred` | PASS |
| US-9 | "not authenticated -- run velmiren auth google first" | `test_cli::TestNoAuthMessage::test_send_without_auth`, `test_list_without_auth` | PASS |
| US-10 | pytest exits 0, coverage >= 80%, no real network | Dynamic validation below | PASS |

---

## Dynamic Validation Log

### 1. `pytest tests/ -v --tb=short`

```
107 passed in 1.44s
```

**Result**: 107 passed, 0 failed. Up from 106 (pass 1) — the apostrophe-escaping test was added.

### 2. `pytest tests/ --cov=src/velmiren --cov-report=term`

```
Name                       Stmts   Miss  Cover
----------------------------------------------
src\velmiren\__init__.py       1      0   100%
src\velmiren\__main__.py       3      3     0%
src\velmiren\auth.py          95     13    86%
src\velmiren\cli.py          101      2    98%
src\velmiren\drive.py         77      2    97%
src\velmiren\errors.py        30      0   100%
src\velmiren\paths.py         73     10    86%
----------------------------------------------
TOTAL                        380     30    92%
```

**Result**: 92% overall. cli.py improved from 91% to 98% (list command refactor eliminated private-API code paths). All modules above 80% except `__main__.py` (entry point, expected).

### 3. `python -m velmiren --help`

```
Usage: python -m velmiren [OPTIONS] COMMAND [ARGS]...
  Velmiren -- file transport to/from Google Drive.
Commands: auth, delete, exists, fetch, list, send, status
```

**Exit code**: 0. PASS.

### 4. `python -m velmiren auth foobar`

```
unsupported provider: foobar
```

**Exit code**: 3. PASS. (Was exit 1 before B-1 fix.)

### 5. `python -m velmiren status`

```
Auth state: not authenticated
Cred file: C:\Users\hazra\.velmiren\cred
not authenticated -- run 'velmiren auth google' first
```

**Exit code**: 2. PASS.

---

## Summary

| Bugs | Gaps | Warnings | Style |
|------|------|----------|-------|
| 0 | 0 | 0 | 2 (carried, non-blocking) |

**Verdict**: PASS (0B / 0W)

All pass-1 findings (1B + 3W) are verified closed. No new issues introduced by the fix iteration. 107 tests passing, 92% coverage, all 5 smoke commands return expected exit codes.
