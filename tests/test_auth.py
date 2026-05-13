"""Tests for velmiren.auth — OAuth flow and token lifecycle."""

from __future__ import annotations

import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest

from velmiren import auth
from velmiren.errors import AuthExpiredError, NetworkError, NotAuthenticatedError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_cred_file(tmp_path: pathlib.Path, data: dict) -> pathlib.Path:
    cred_dir = tmp_path / ".velmiren"
    cred_dir.mkdir()
    cred_file = cred_dir / "cred"
    cred_file.write_text(json.dumps(data), encoding="utf-8")
    return cred_file


# ---------------------------------------------------------------------------
# _cred_path
# ---------------------------------------------------------------------------


class TestCredPath:
    def test_ends_with_cred(self):
        p = auth._cred_path()
        assert p.name == "cred"
        assert p.parent.name == ".velmiren"


# ---------------------------------------------------------------------------
# _get_client_config
# ---------------------------------------------------------------------------


class TestGetClientConfig:
    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("VELMIREN_OAUTH_CLIENT_ID", raising=False)
        monkeypatch.delenv("VELMIREN_OAUTH_CLIENT_SECRET", raising=False)
        cid, csec = auth._get_client_config()
        assert cid == auth._DEFAULT_CLIENT_ID
        assert csec == auth._DEFAULT_CLIENT_SECRET

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("VELMIREN_OAUTH_CLIENT_ID", "my-id")
        monkeypatch.setenv("VELMIREN_OAUTH_CLIENT_SECRET", "my-secret")
        cid, csec = auth._get_client_config()
        assert cid == "my-id"
        assert csec == "my-secret"


# ---------------------------------------------------------------------------
# _build_client_config
# ---------------------------------------------------------------------------


class TestBuildClientConfig:
    def test_structure(self):
        cfg = auth._build_client_config("cid", "csec")
        assert "installed" in cfg
        inst = cfg["installed"]
        assert inst["client_id"] == "cid"
        assert inst["client_secret"] == "csec"
        assert "token_uri" in inst
        assert "auth_uri" in inst


# ---------------------------------------------------------------------------
# _atomic_write_cred
# ---------------------------------------------------------------------------


class TestAtomicWriteCred:
    def test_writes_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(auth, "_cred_path", lambda: tmp_path / ".velmiren" / "cred")
        data = {"key": "value"}
        auth._atomic_write_cred(data)
        written = json.loads((tmp_path / ".velmiren" / "cred").read_text())
        assert written == data

    def test_creates_parent_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(auth, "_cred_path", lambda: tmp_path / "new_dir" / "cred")
        auth._atomic_write_cred({"a": 1})
        assert (tmp_path / "new_dir" / "cred").exists()

    def test_exception_leaves_original_intact(self, tmp_path, monkeypatch):
        cred_path = tmp_path / ".velmiren" / "cred"
        (tmp_path / ".velmiren").mkdir()
        cred_path.write_text('{"original": true}', encoding="utf-8")
        monkeypatch.setattr(auth, "_cred_path", lambda: cred_path)

        # Make json.dump raise after mkstemp
        with patch("json.dump", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                auth._atomic_write_cred({"new": True})

        # Original file must be intact
        assert json.loads(cred_path.read_text()) == {"original": True}


# ---------------------------------------------------------------------------
# _read_cred_file
# ---------------------------------------------------------------------------


class TestReadCredFile:
    def test_raises_if_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(auth, "_cred_path", lambda: tmp_path / "nonexistent" / "cred")
        with pytest.raises(NotAuthenticatedError):
            auth._read_cred_file()

    def test_raises_if_corrupt(self, tmp_path, monkeypatch):
        cred_path = tmp_path / "cred"
        cred_path.write_text("not-json", encoding="utf-8")
        monkeypatch.setattr(auth, "_cred_path", lambda: cred_path)
        with pytest.raises(NotAuthenticatedError):
            auth._read_cred_file()

    def test_raises_if_missing_fields(self, tmp_path, monkeypatch):
        cred_path = tmp_path / "cred"
        cred_path.write_text('{"refresh_token": "x"}', encoding="utf-8")
        monkeypatch.setattr(auth, "_cred_path", lambda: cred_path)
        with pytest.raises(NotAuthenticatedError):
            auth._read_cred_file()

    def test_returns_dict_on_valid_file(self, tmp_path, monkeypatch, fake_cred_data):
        cred_path = tmp_path / "cred"
        cred_path.write_text(json.dumps(fake_cred_data), encoding="utf-8")
        monkeypatch.setattr(auth, "_cred_path", lambda: cred_path)
        data = auth._read_cred_file()
        assert data["email"] == "test@example.com"


# ---------------------------------------------------------------------------
# _handle_refresh_error
# ---------------------------------------------------------------------------


class TestHandleRefreshError:
    def test_invalid_grant_raises_auth_expired(self):
        with pytest.raises(AuthExpiredError):
            auth._handle_refresh_error(Exception("invalid_grant"))

    def test_other_raises_network_error(self):
        with pytest.raises(NetworkError):
            auth._handle_refresh_error(Exception("connection refused"))


# ---------------------------------------------------------------------------
# _serialize_cred
# ---------------------------------------------------------------------------


class TestSerializeCred:
    def test_six_fields(self):
        fake = MagicMock()
        fake.refresh_token = "rt"
        fake.client_id = "cid"
        fake.client_secret = "cs"
        fake.token_uri = "https://oauth2.googleapis.com/token"
        result = auth._serialize_cred(fake, "user@example.com")
        assert set(result.keys()) == {"refresh_token", "client_id", "client_secret", "token_uri", "scope", "email"}
        assert result["email"] == "user@example.com"


# ---------------------------------------------------------------------------
# run_oauth_flow (US-1 happy path)
# ---------------------------------------------------------------------------


class TestRunOAuthFlow:
    def test_happy_path_returns_cred_dict(self):
        fake_user_cred = MagicMock()
        fake_user_cred.refresh_token = "rt"
        fake_user_cred.client_id = "cid"
        fake_user_cred.client_secret = "cs"
        fake_user_cred.token_uri = "https://oauth2.googleapis.com/token"
        fake_user_cred.token = "at"

        with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_config") as mock_flow_cls:
            mock_flow = MagicMock()
            mock_flow.run_local_server.return_value = fake_user_cred
            mock_flow_cls.return_value = mock_flow

            with patch.object(auth, "_fetch_email", return_value="user@example.com"):
                result = auth.run_oauth_flow("cid", "cs")

        assert result["email"] == "user@example.com"
        assert "refresh_token" in result

    def test_flow_failure_propagates(self):
        with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_config") as mock_flow_cls:
            mock_flow = MagicMock()
            mock_flow.run_local_server.side_effect = RuntimeError("user cancelled")
            mock_flow_cls.return_value = mock_flow

            with pytest.raises(RuntimeError, match="user cancelled"):
                auth.run_oauth_flow("cid", "cs")


# ---------------------------------------------------------------------------
# load (US-7, US-9)
# ---------------------------------------------------------------------------


class TestLoad:
    def test_happy_path_returns_cred(self, fake_cred_data):
        with patch.object(auth, "_read_cred_file", return_value=fake_cred_data):
            with patch.object(auth, "_build_credential") as mock_build:
                with patch("google.auth.transport.requests.Request"):
                    fake_cred = MagicMock()
                    fake_cred.refresh.return_value = None
                    mock_build.return_value = fake_cred
                    result = auth.load()
                    assert result is fake_cred

    def test_missing_cred_file_raises(self):
        with patch.object(auth, "_read_cred_file", side_effect=NotAuthenticatedError()):
            with pytest.raises(NotAuthenticatedError):
                auth.load()

    def test_invalid_grant_raises_auth_expired(self, fake_cred_data):
        with patch.object(auth, "_read_cred_file", return_value=fake_cred_data):
            with patch.object(auth, "_build_credential") as mock_build:
                with patch("google.auth.transport.requests.Request"):
                    fake_cred = MagicMock()
                    fake_cred.refresh.side_effect = Exception("invalid_grant")
                    mock_build.return_value = fake_cred
                    with pytest.raises(AuthExpiredError):
                        auth.load()


# ---------------------------------------------------------------------------
# get_status (US-7)
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_not_authenticated(self, tmp_path, monkeypatch):
        monkeypatch.setattr(auth, "_cred_path", lambda: tmp_path / "missing" / "cred")
        status = auth.get_status()
        assert not status["authenticated"]

    def test_authenticated(self, tmp_path, monkeypatch, fake_cred_data):
        cred_path = tmp_path / "cred"
        cred_path.write_text(json.dumps(fake_cred_data), encoding="utf-8")
        monkeypatch.setattr(auth, "_cred_path", lambda: cred_path)
        status = auth.get_status()
        assert status["authenticated"]
        assert status["email"] == "test@example.com"


# ---------------------------------------------------------------------------
# re-auth (US-8): failed OAuth leaves original cred intact
# ---------------------------------------------------------------------------


class TestReAuth:
    def test_failed_flow_leaves_original_cred(self, tmp_path, monkeypatch, fake_cred_data):
        cred_path = tmp_path / ".velmiren" / "cred"
        (tmp_path / ".velmiren").mkdir()
        cred_path.write_text(json.dumps(fake_cred_data), encoding="utf-8")
        monkeypatch.setattr(auth, "_cred_path", lambda: cred_path)

        with patch.object(auth, "run_oauth_flow", side_effect=RuntimeError("network error")):
            with pytest.raises(RuntimeError):
                data = auth.run_oauth_flow("cid", "cs")

        # Original cred must be intact
        assert json.loads(cred_path.read_text())["email"] == "test@example.com"
