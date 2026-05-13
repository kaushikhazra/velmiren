"""Tests for velmiren.cli — Click commands via CliRunner."""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from velmiren.cli import main
from velmiren.errors import (
    AuthExpiredError,
    NetworkError,
    NotAuthenticatedError,
    RemoteNotFoundError,
    UserError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(args, **kwargs):
    runner = CliRunner()
    return runner.invoke(main, args, catch_exceptions=False, **kwargs)


def _run_catching(args, **kwargs):
    runner = CliRunner()
    return runner.invoke(main, args, catch_exceptions=True, **kwargs)


# ---------------------------------------------------------------------------
# --help
# ---------------------------------------------------------------------------


class TestHelp:
    def test_root_help_exits_zero(self):
        result = _run(["--help"])
        assert result.exit_code == 0
        assert "velmiren" in result.output.lower() or "Usage" in result.output

    def test_send_help(self):
        result = _run(["send", "--help"])
        assert result.exit_code == 0

    def test_fetch_help(self):
        result = _run(["fetch", "--help"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# auth (US-1)
# ---------------------------------------------------------------------------


class TestAuthCommand:
    def test_happy_path_prints_ok(self, fake_cred_data):
        fake_cred_data["email"] = "user@example.com"
        with patch("velmiren.cli.auth.run_oauth_flow", return_value=fake_cred_data):
            with patch("velmiren.cli.auth._get_client_config", return_value=("cid", "cs")):
                with patch("velmiren.cli.auth._atomic_write_cred"):
                    result = _run(["auth", "google"])

        assert "OK" in result.output
        assert "user@example.com" in result.output
        assert result.exit_code == 0

    def test_unknown_provider_exits_three(self):
        result = _run_catching(["auth", "dropbox"])
        assert result.exit_code == 3


# ---------------------------------------------------------------------------
# status (US-7)
# ---------------------------------------------------------------------------


class TestStatusCommand:
    def test_not_authenticated_exits_nonzero(self):
        with patch("velmiren.cli.auth.get_status", return_value={
            "authenticated": False,
            "cred_path": "/fake/.velmiren/cred",
        }):
            runner = CliRunner()
            result = runner.invoke(main, ["status"], catch_exceptions=True)

        assert result.exit_code != 0
        assert "not authenticated" in result.output

    def test_authenticated_exits_zero(self, fake_cred):
        fake_cred.expiry = None
        with patch("velmiren.cli.auth.get_status", return_value={
            "authenticated": True,
            "email": "user@example.com",
            "cred_path": "/fake/.velmiren/cred",
        }):
            with patch("velmiren.cli.auth.load", return_value=fake_cred):
                result = _run(["status"])

        assert result.exit_code == 0
        assert "authenticated" in result.output
        assert "user@example.com" in result.output


# ---------------------------------------------------------------------------
# send (US-2)
# ---------------------------------------------------------------------------


class TestSendCommand:
    def test_happy_path_prints_file_id(self, tmp_path, fake_cred):
        local = tmp_path / "report.pdf"
        local.write_bytes(b"data")

        with patch("velmiren.cli.auth.load", return_value=fake_cred):
            with patch("velmiren.cli.drive.upload", return_value="drive-file-id"):
                result = _run(["send", str(local), "--to", "/velmiren/report.pdf"])

        assert "drive-file-id" in result.output
        assert result.exit_code == 0

    def test_not_authenticated_exits_two(self, tmp_path):
        local = tmp_path / "report.pdf"
        local.write_bytes(b"data")

        with patch("velmiren.cli.auth.load", side_effect=NotAuthenticatedError()):
            runner = CliRunner()
            result = runner.invoke(main, ["send", str(local), "--to", "/velmiren/r.pdf"], catch_exceptions=True)

        assert result.exit_code == 2
        assert "not authenticated" in result.output

    def test_missing_to_flag_exits_nonzero(self, tmp_path):
        local = tmp_path / "report.pdf"
        local.write_bytes(b"data")
        result = _run_catching(["send", str(local)])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# fetch (US-4)
# ---------------------------------------------------------------------------


class TestFetchCommand:
    def test_happy_path_prints_bytes(self, tmp_path, fake_cred):
        with patch("velmiren.cli.auth.load", return_value=fake_cred):
            with patch("velmiren.cli.drive.download", return_value=1024):
                result = _run(["fetch", "/velmiren/notes.txt", "--to", str(tmp_path / "out.txt")])

        assert "1024" in result.output
        assert result.exit_code == 0

    def test_remote_not_found_exits_one(self, tmp_path, fake_cred):
        with patch("velmiren.cli.auth.load", return_value=fake_cred):
            with patch("velmiren.cli.drive.download", side_effect=RemoteNotFoundError("no such remote file")):
                runner = CliRunner()
                result = runner.invoke(main, ["fetch", "/velmiren/missing.txt", "--to", str(tmp_path / "out.txt")], catch_exceptions=True)

        assert result.exit_code == 1

    def test_not_authenticated_exits_two(self, tmp_path):
        with patch("velmiren.cli.auth.load", side_effect=NotAuthenticatedError()):
            runner = CliRunner()
            result = runner.invoke(main, ["fetch", "/velmiren/f.txt", "--to", str(tmp_path / "out.txt")], catch_exceptions=True)

        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# list (US-3)
# ---------------------------------------------------------------------------


class TestListCommand:
    def test_happy_path_lists_files(self, fake_cred):
        files = [
            {"name": "a.txt", "size": "100", "modifiedTime": "2025-01-01T00:00:00Z", "id": "id1"}
        ]
        with patch("velmiren.cli.auth.load", return_value=fake_cred):
            with patch("velmiren.cli.drive._service", return_value=MagicMock()):
                with patch("velmiren.cli.paths.resolve", return_value="folder-id"):
                    with patch("velmiren.cli.drive.list_dir", return_value=files):
                        result = _run(["list", "/velmiren"])

        assert "a.txt" in result.output
        assert result.exit_code == 0

    def test_empty_folder_exits_zero(self, fake_cred):
        with patch("velmiren.cli.auth.load", return_value=fake_cred):
            with patch("velmiren.cli.drive._service", return_value=MagicMock()):
                with patch("velmiren.cli.paths.resolve", return_value="folder-id"):
                    with patch("velmiren.cli.drive.list_dir", return_value=[]):
                        result = _run(["list", "/velmiren"])

        assert result.output.strip() == ""
        assert result.exit_code == 0

    def test_nonexistent_folder_exits_one(self, fake_cred):
        with patch("velmiren.cli.auth.load", return_value=fake_cred):
            with patch("velmiren.cli.drive._service", return_value=MagicMock()):
                with patch("velmiren.cli.paths.resolve", side_effect=RemoteNotFoundError("no such remote folder")):
                    runner = CliRunner()
                    result = runner.invoke(main, ["list", "/velmiren/nope"], catch_exceptions=True)

        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# exists (US-5)
# ---------------------------------------------------------------------------


class TestExistsCommand:
    def test_prints_true_exits_zero(self, fake_cred):
        with patch("velmiren.cli.auth.load", return_value=fake_cred):
            with patch("velmiren.cli.drive.file_exists", return_value=True):
                result = _run(["exists", "/velmiren/foo.pdf"])

        assert "true" in result.output
        assert result.exit_code == 0

    def test_prints_false_exits_one(self, fake_cred):
        with patch("velmiren.cli.auth.load", return_value=fake_cred):
            with patch("velmiren.cli.drive.file_exists", return_value=False):
                runner = CliRunner()
                result = runner.invoke(main, ["exists", "/velmiren/missing.pdf"], catch_exceptions=True)

        assert "false" in result.output
        assert result.exit_code == 1

    def test_auth_failure_exits_two(self):
        with patch("velmiren.cli.auth.load", side_effect=NotAuthenticatedError()):
            runner = CliRunner()
            result = runner.invoke(main, ["exists", "/velmiren/foo.pdf"], catch_exceptions=True)

        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# delete (US-6)
# ---------------------------------------------------------------------------


class TestDeleteCommand:
    def test_happy_path_exits_zero(self, fake_cred):
        with patch("velmiren.cli.auth.load", return_value=fake_cred):
            with patch("velmiren.cli.drive.delete_file"):
                result = _run(["delete", "/velmiren/old.tmp", "--force"])

        assert result.exit_code == 0

    def test_no_force_exits_three(self, fake_cred):
        with patch("velmiren.cli.auth.load", return_value=fake_cred):
            runner = CliRunner()
            result = runner.invoke(main, ["delete", "/velmiren/old.tmp"], catch_exceptions=True)

        assert result.exit_code == 3
        assert "--force required" in result.output

    def test_not_found_exits_one(self, fake_cred):
        with patch("velmiren.cli.auth.load", return_value=fake_cred):
            with patch("velmiren.cli.drive.delete_file", side_effect=RemoteNotFoundError("no such remote file")):
                runner = CliRunner()
                result = runner.invoke(main, ["delete", "/velmiren/missing.tmp", "--force"], catch_exceptions=True)

        assert result.exit_code == 1

    def test_not_authenticated_exits_two(self):
        with patch("velmiren.cli.auth.load", side_effect=NotAuthenticatedError()):
            runner = CliRunner()
            result = runner.invoke(main, ["delete", "/velmiren/f.tmp", "--force"], catch_exceptions=True)

        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# US-9: any command without auth prints helpful message
# ---------------------------------------------------------------------------


class TestNoAuthMessage:
    def test_send_without_auth(self, tmp_path):
        local = tmp_path / "f.txt"
        local.write_bytes(b"x")
        with patch("velmiren.cli.auth.load", side_effect=NotAuthenticatedError()):
            runner = CliRunner()
            result = runner.invoke(main, ["send", str(local), "--to", "/velmiren/f.txt"], catch_exceptions=True)

        assert "not authenticated" in result.output
        assert "velmiren auth google" in result.output

    def test_list_without_auth(self):
        with patch("velmiren.cli.auth.load", side_effect=NotAuthenticatedError()):
            runner = CliRunner()
            result = runner.invoke(main, ["list"], catch_exceptions=True)

        assert "not authenticated" in result.output

    def test_expired_auth_shows_correct_message(self):
        with patch("velmiren.cli.auth.load", side_effect=AuthExpiredError()):
            runner = CliRunner()
            result = runner.invoke(main, ["list"], catch_exceptions=True)

        assert "expired" in result.output
        assert result.exit_code == 2
