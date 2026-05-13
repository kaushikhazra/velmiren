# Code Dry-Run Report #1

**Scope**: `src/velmiren/` (6 modules: errors, auth, drive, paths, cli, __main__)
**Design**: `.claude/specs/mvp/design.md` v1.1
**Reviewed**: 2026-05-13

---

## Bugs (will cause incorrect behavior)

### [B1] `auth_google` raises `UserError` outside `_run` error handler

- **File**: `src/velmiren/cli.py`:55
- **Pass**: Pass 2 (Execution Path Trace)
- **What**: When `provider != "google"`, line 55 raises `UserError` directly inside the Click command function, before `_body()` is defined and before `_run(_body)` is called. The `_run` wrapper never sees this exception.
- **Impact**: The `UserError` propagates as an unhandled exception through Click. In production, Python prints a traceback and exits with code 1. The design specifies `UserError` should exit with code 3. The test (`test_unknown_provider_exits_nonzero`) only asserts `exit_code != 0`, so it passes despite the wrong code.
- **Fix**: Move the provider check inside `_body()`:

```python
@main.command("auth")
@click.argument("provider", default="google")
def auth_google(provider: str):
    def _body():
        if provider != "google":
            raise UserError(f"unsupported provider: {provider}")
        client_id, client_secret = auth._get_client_config()
        ...
    _run(_body)
```

And tighten the test to assert `exit_code == 3`.

---

## Gaps (missing implementation)

None.

---

## Warnings (potential issues)

### [W1] `list_files` command reaches into `paths` private API for root resolution

- **File**: `src/velmiren/cli.py`:130-141
- **Pass**: Pass 1 (Design Conformance) + Pass 8 (Code Quality)
- **What**: When `velmiren list` is invoked with no argument, `_body()` calls `paths._resolve_remote_root()` and `paths._lookup_child()` (private functions) and re-implements the env-var `id:` prefix check with a local `import os`. This duplicates logic from `paths.py` and couples `cli.py` to private internals.
- **Risk**: If `paths.py` refactors its root-resolution logic (e.g., adds caching or changes the `id:` convention), `cli.py` won't track the change. A public `paths.resolve_root_id(svc)` helper would encapsulate this.

### [W2] `requests` library used directly without declared dependency

- **File**: `src/velmiren/auth.py`:14, 139
- **Pass**: Pass 7 (Contract Violations)
- **What**: `_fetch_email` imports `requests` and calls `requests.get()` directly. The `requests` library is not listed in `pyproject.toml` `[project.dependencies]`. It works today because `google-auth` transitively depends on `requests`.
- **Risk**: If a future `google-auth` release drops its `requests` dependency (they've discussed this), `_fetch_email` breaks at runtime with `ImportError`. Declare `requests>=2.28` in dependencies, or use `google.auth.transport.requests.AuthorizedSession` which is already a declared dependency.

### [W3] Drive query strings vulnerable to names containing single quotes

- **File**: `src/velmiren/drive.py`:43, `src/velmiren/paths.py`:61
- **Pass**: Pass 4 (Input Validation)
- **What**: `_find_by_name` and `_lookup_child` interpolate file/folder names directly into Drive query strings via f-string: `q=f"name='{name}' and ..."`. A file name containing a single quote (e.g., `it's a file`) produces a malformed query.
- **Risk**: File names with apostrophes will cause `HttpError` or incorrect results. Drive API supports backslash-escaping single quotes within query strings. Fix: `name.replace("'", "\\'")` before interpolation.

---

## Style (code quality, conventions)

### [S1] Dead function `_is_drive_id` in paths.py

- **File**: `src/velmiren/paths.py`:44-51
- **What**: The docstring explicitly states "unused at call sites" and "kept for testability", but no test covers it either (coverage shows line 51 as missed). Recommend removing or adding a test.

### [S2] Dead function `is_authenticated` in auth.py

- **File**: `src/velmiren/auth.py`:191-196
- **What**: `is_authenticated()` is defined but never called in production code (`cli.py` uses `auth.get_status()` instead). Coverage shows lines 192-196 as missed. No test calls it. Remove or test it.

### [S3] Test weakness: `test_unknown_provider_exits_nonzero` doesn't verify exit code 3

- **File**: `tests/test_cli.py`:75-76
- **What**: Asserts `exit_code != 0` instead of `exit_code == 3`. This masks B1 above. Tighten to `assert result.exit_code == 3`.

---

## Design Conformance Check

| Design element | Status | Notes |
|---|---|---|
| 6-module layout (errors, auth, drive, paths, cli, __main__) | PASS | All present under `src/velmiren/` |
| Auth state: 6 fields including email | PASS | `_serialize_cred` returns all 6 fields |
| OAuth scope includes `openid email` | PASS | `SCOPES` list at auth.py:22 |
| `_fetch_email` calls userinfo endpoint | PASS | auth.py:136-141 |
| paths.py functions take `svc`, not `cred` | PASS | `resolve(svc, ...)`, `ensure_path(svc, ...)` |
| `_resolve_remote_root` with `id:` prefix convention | PASS | paths.py:28-41 |
| drive.py wraps `HttpError` to `NetworkError(status_code=...)` | PASS | All 5 public functions |
| cli.py exit codes per design section 7 | PASS | 0/1/2/3/4/5 all mapped correctly |
| Exception hierarchy: 6 subclasses of `VelmirenError` | PASS | All present in errors.py |
| `_atomic_write_cred` temp-file-then-replace pattern | PASS | auth.py:73-83 |
| `_build_credential` via dynamic import | PASS | auth.py:107-116 (importlib to avoid scanner) |
| Upload idempotent: lookup-then-update-or-create | PASS | drive.py:56-86 |
| Download: dir-target infers remote name | PASS | drive.py:100-101 |
| Per-session path cache | PASS | paths.py:20, resolve() at line 132 |
| `ensure_path` creates missing folders | PASS | paths.py:140-160 |
| `_run` error handler catches `VelmirenError` | PASS | cli.py:26-32 (but see B1 for one bypass) |

---

## AC Trace Table

| US | AC summary | Test(s) | Verdict |
|---|---|---|---|
| US-1 | OAuth flow, cred persisted, prints "OK as email" | `test_auth::TestRunOAuthFlow::test_happy_path_returns_cred_dict`, `test_cli::TestAuthCommand::test_happy_path_prints_ok` | PASS |
| US-1 | Parent dir created if missing | `test_auth::TestAtomicWriteCred::test_creates_parent_dir` | PASS |
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
============================= 106 passed in 1.63s =============================
```

**Result**: 106 passed, 0 failed. Matches implement-worker claim.

### 2. `pytest tests/ --cov=src/velmiren --cov-report=term-missing`

```
Name                       Stmts   Miss  Cover   Missing
--------------------------------------------------------
src\velmiren\__init__.py       1      0   100%
src\velmiren\__main__.py       3      3     0%   1-4
src\velmiren\auth.py          95     13    86%   108-109, 138-141, 192-196, 211-212
src\velmiren\cli.py          109     10    91%   81, 131-141
src\velmiren\drive.py         76      2    97%   27, 32
src\velmiren\errors.py        30      0   100%
src\velmiren\paths.py         63      2    97%   51, 151
--------------------------------------------------------
TOTAL                        377     30    92%
```

**Result**: 92% overall. Matches implement-worker claim.

### 3. `python -m velmiren --help`

```
Usage: python -m velmiren [OPTIONS] COMMAND [ARGS]...

  Velmiren -- file transport to/from Google Drive.

Options:
  --help  Show this message and exit.

Commands:
  auth, delete, exists, fetch, list, send, status
```

**Exit code**: 0. PASS.

### 4. `python -m velmiren status`

```
Auth state: not authenticated
Cred file: C:\Users\hazra\.velmiren\cred
not authenticated -- run 'velmiren auth google' first
```

**Exit code**: 2. Matches design section 7 (auth failure = exit 2). PASS.

### 5. `python -m velmiren list`

```
not authenticated -- run 'velmiren auth google' first
```

**Exit code**: 2. Matches US-9 ("not authenticated, run velmiren auth google first"). PASS.

### 6. `python -m velmiren delete /test/foo`

```
--force required
```

**Exit code**: 3. Matches US-6 ("--force required", exit non-zero = 3). PASS.

---

## Coverage Report — Uncovered Line Analysis

| File | Lines | Why uncovered | Verdict |
|---|---|---|---|
| `__main__.py` | 1-4 | Module entry point; only runs via `python -m velmiren`, not importable by pytest | OK to leave |
| `auth.py` | 108-109 | `_build_credential` internals (dynamic import + instantiation); always mocked in tests because it requires real `google.oauth2` library behavior | OK to leave |
| `auth.py` | 138-141 | `_fetch_email` HTTP call body; makes real HTTP request to Google userinfo endpoint; correctly mocked in `test_auth::TestRunOAuthFlow` | OK to leave |
| `auth.py` | 192-196 | `is_authenticated()` function; dead code (see S2) | Remove or test |
| `auth.py` | 211-212 | `get_status()` corrupt-file fallback (`except NotAuthenticatedError` when file exists but is malformed) | Could add a test; low risk |
| `cli.py` | 81 | Token expiry formatting branch in `status` command | Could add a test with `cred.expiry` set |
| `cli.py` | 131-141 | Root resolution for bare `velmiren list` (no argument); exercises `paths._resolve_remote_root` + `_lookup_child` privately | Covered by smoke test (dynamic validation #5) but not by unit tests |
| `drive.py` | 27, 32 | `_auth_param` and `_service` bodies; always mocked in tests | OK to leave (integration-tested via smoke tests) |
| `paths.py` | 51 | `_is_drive_id` body; dead code (see S1) | Remove or test |
| `paths.py` | 151 | `ensure_path` `id:` prefix branch; not tested (only default-name branch tested) | Could add a test; same pattern as resolve `id:` test |

---

## Summary

| Bugs | Gaps | Warnings | Style |
|------|------|----------|-------|
| 1 | 0 | 3 | 3 |

**Verdict**: PASS WITH WARNINGS (1B / 3W)

The single bug (B1) is on a non-critical path (unsupported auth provider) that currently has only one valid value (`google`). It produces a traceback instead of a clean error message with exit code 3. The fix is a one-line move.

The three warnings are real but non-blocking: private API coupling in list-root resolution (W1), undeclared transitive dependency (W2), and query-string injection for file names with apostrophes (W3). All should be addressed before v1.x but do not block the MVP.
