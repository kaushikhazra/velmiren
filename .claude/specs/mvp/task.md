# Velmiren MVP — Tasks

## A. Module Skeletons

- [x] Implementor creates `src/velmiren/__main__.py` stub — _US-2_
- [x] Implementor creates `src/velmiren/errors.py` stub — _US-9_
- [x] Implementor creates `src/velmiren/auth.py` stub — _US-1_
- [x] Implementor creates `src/velmiren/paths.py` stub — _US-2_
- [x] Implementor creates `src/velmiren/drive.py` stub — _US-2_
- [x] Implementor creates `src/velmiren/cli.py` stub — _US-2_

## B. errors.py — Exception Hierarchy

- [x] Implementor writes `VelmirenError` base class with `exit_code` and `message` in `errors.py` — _US-9_
- [x] Implementor writes `NotAuthenticatedError`, `AuthExpiredError`, `RemoteNotFoundError`, `UserError`, `NetworkError`, `SizeCapError` subclasses in `errors.py` — _US-9_
- [x] Implementor writes exit-code constants (EXIT_SUCCESS=0 through EXIT_SIZE_CAP=5) in `errors.py` — _US-9_

## C. auth.py — OAuth Flow and Token Lifecycle

- [x] Implementor writes `_DEFAULT_CLIENT_ID`, `_DEFAULT_CLIENT_SECRET`, `SCOPES`, `_cred_path()` in `auth.py` — _US-1_
- [x] Implementor writes `_build_client_config()`, `_get_client_config()`, `run_oauth_flow()` in `auth.py` — _US-1_
- [x] Implementor writes `_fetch_email()`, `_serialize_cred()`, `_atomic_write_cred()` in `auth.py` — _US-1_
- [x] Implementor writes `_read_cred_file()`, `_build_credential()`, `_handle_refresh_error()`, `load()` in `auth.py` — _US-7_
- [x] Implementor writes `is_authenticated()`, `get_status()` helpers in `auth.py` — _US-7_

## D. drive.py — Drive API Wrapper

- [x] Implementor writes `_auth_param()`, `_service()`, `_find_by_name()` in `drive.py` — _US-2_
- [x] Implementor writes `upload()` with idempotent logic and SizeCap check in `drive.py` — _US-2_
- [x] Implementor writes `download()` with dir-target logic in `drive.py` — _US-4_
- [x] Implementor writes `list_dir()` in `drive.py` — _US-3_
- [x] Implementor writes `file_exists()` in `drive.py` — _US-5_
- [x] Implementor writes `delete_file()` in `drive.py` — _US-6_
- [x] Implementor wraps all public functions with `HttpError → NetworkError` in `drive.py` — _US-9_

## E. paths.py — Remote Path Resolution

- [x] Implementor writes `_DEFAULT_ROOT_FOLDER`, `_cache`, `_resolve_remote_root()` in `paths.py` — _US-2_
- [x] Implementor writes `_walk()` with folder/file segment lookup in `paths.py` — _US-2_
- [x] Implementor writes `resolve()` with per-session cache in `paths.py` — _US-3_
- [x] Implementor writes `_get_or_create_folder()`, `ensure_path()` in `paths.py` — _US-2_

## F. cli.py — Click Commands

- [x] Implementor writes `main` Click group, `_run()` error handler in `cli.py` — _US-9_
- [x] Implementor writes `auth_google` command (triggers OAuth flow, prints OK message) in `cli.py` — _US-1_
- [x] Implementor writes `status` command (prints auth state, email, expiry, cred path) in `cli.py` — _US-7_
- [x] Implementor writes `send` command (`--to` required, calls `drive.upload`) in `cli.py` — _US-2_
- [x] Implementor writes `fetch` command (`--to` required, calls `drive.download`) in `cli.py` — _US-4_
- [x] Implementor writes `list_files` command (optional remote_dir arg, calls `drive.list_dir`) in `cli.py` — _US-3_
- [x] Implementor writes `exists` command (prints true/false, exit 0/1) in `cli.py` — _US-5_
- [x] Implementor writes `delete` command (`--force` required, calls `drive.delete_file`) in `cli.py` — _US-6_

## G. pyproject.toml — Dependencies

- [x] Implementor updates `[project.dependencies]` with click, google-auth, google-auth-oauthlib, google-api-python-client in `pyproject.toml` — _US-10_
- [x] Implementor updates `[project.optional-dependencies] dev` with pytest-mock, pytest-cov in `pyproject.toml` — _US-10_

## H. Tests

- [x] Implementor writes `tests/conftest.py` with `fake_drive_service`, `fake_cred`, `fake_cred_data` fixtures — _US-10_
- [x] Implementor writes `tests/test_errors.py` covering exception hierarchy and exit codes — _US-10_
- [x] Implementor writes `tests/test_auth.py` covering US-1, US-7, US-8, US-9 happy + error paths — _US-10_
- [x] Implementor writes `tests/test_paths.py` covering resolve, cache, ensure_path, RemoteNotFoundError — _US-10_
- [x] Implementor writes `tests/test_drive.py` covering upload (create + update), download, list, exists, delete — _US-10_
- [x] Implementor writes `tests/test_cli.py` covering all 8 commands happy + error via Click CliRunner — _US-10_
- [x] Implementor runs `pytest tests/ --cov=src/velmiren --cov-fail-under=80` and confirms ≥80% coverage — _US-10_
