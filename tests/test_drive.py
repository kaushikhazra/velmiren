"""Tests for velmiren.drive — Drive API wrapper."""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import pytest

from velmiren import drive, paths
from velmiren.errors import NetworkError, RemoteNotFoundError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_http_error(status: int = 500, reason: str = "Server Error"):
    """Build a fake googleapiclient.errors.HttpError."""
    from googleapiclient.errors import HttpError
    resp = MagicMock()
    resp.status = status
    resp.reason = reason
    return HttpError(resp=resp, content=b"error")


# ---------------------------------------------------------------------------
# _find_by_name
# ---------------------------------------------------------------------------


class TestFindByName:
    def test_returns_id_when_found(self, fake_drive_service):
        fake_drive_service.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "found-id"}]
        }
        result = drive._find_by_name(fake_drive_service, "foo.pdf", "parent-id")
        assert result == "found-id"

    def test_returns_none_when_not_found(self, fake_drive_service):
        fake_drive_service.files.return_value.list.return_value.execute.return_value = {"files": []}
        result = drive._find_by_name(fake_drive_service, "foo.pdf", "parent-id")
        assert result is None

    def test_apostrophe_in_name_is_escaped(self, fake_drive_service):
        """W-3: file names with single quotes must not break the Drive query string."""
        fake_drive_service.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "found-id"}]
        }
        result = drive._find_by_name(fake_drive_service, "can't.txt", "parent-id")
        assert result == "found-id"
        # Verify the query string carried the backslash-escaped apostrophe
        call_kwargs = fake_drive_service.files.return_value.list.call_args.kwargs
        assert "can\\'t.txt" in call_kwargs["q"]


# ---------------------------------------------------------------------------
# upload
# ---------------------------------------------------------------------------


class TestUpload:
    def test_create_new_file(self, tmp_path, fake_cred):
        local = tmp_path / "report.pdf"
        local.write_bytes(b"x" * 100)

        with patch.object(drive, "_service") as mock_svc:
            svc = MagicMock()
            mock_svc.return_value = svc

            with patch.object(paths, "ensure_path", return_value=("parent-id", "report.pdf")):
                with patch.object(drive, "_find_by_name", return_value=None):
                    request = svc.files.return_value.create.return_value
                    request.next_chunk.return_value = (None, {"id": "new-file-id"})
                    with patch("velmiren.drive.MediaFileUpload"):
                        result = drive.upload(fake_cred, str(local), "/velmiren/report.pdf")

        assert result == "new-file-id"

    def test_update_existing_file(self, tmp_path, fake_cred):
        local = tmp_path / "report.pdf"
        local.write_bytes(b"x" * 100)

        with patch.object(drive, "_service") as mock_svc:
            svc = MagicMock()
            mock_svc.return_value = svc

            with patch.object(paths, "ensure_path", return_value=("parent-id", "report.pdf")):
                with patch.object(drive, "_find_by_name", return_value="existing-id"):
                    request = svc.files.return_value.update.return_value
                    request.next_chunk.return_value = (None, {"id": "existing-id"})
                    with patch("velmiren.drive.MediaFileUpload"):
                        result = drive.upload(fake_cred, str(local), "/velmiren/report.pdf")

        assert result == "existing-id"

    def test_resumable_chunks_invoke_progress(self, tmp_path, fake_cred):
        """Multi-chunk upload calls progress callback for each chunk + a final 100% call."""
        local = tmp_path / "movie.mp4"
        local.write_bytes(b"x" * 100)

        progress_calls = []

        def progress(uploaded, total):
            progress_calls.append((uploaded, total))

        with patch.object(drive, "_service") as mock_svc:
            svc = MagicMock()
            mock_svc.return_value = svc
            with patch.object(paths, "ensure_path", return_value=("parent-id", "movie.mp4")):
                with patch.object(drive, "_find_by_name", return_value=None):
                    request = svc.files.return_value.create.return_value
                    status_30 = MagicMock(resumable_progress=30)
                    status_70 = MagicMock(resumable_progress=70)
                    request.next_chunk.side_effect = [
                        (status_30, None),
                        (status_70, None),
                        (None, {"id": "big-id"}),
                    ]
                    with patch("velmiren.drive.MediaFileUpload"):
                        with patch("pathlib.Path.stat") as mock_stat:
                            mock_stat.return_value.st_size = 100
                            result = drive.upload(
                                fake_cred, str(local), "/velmiren/movie.mp4",
                                progress=progress,
                            )

        assert result == "big-id"
        # Two mid-upload progress reports + one final-100 report
        assert progress_calls == [(30, 100), (70, 100), (100, 100)]

    def test_http_error_raises_network_error(self, tmp_path, fake_cred):
        local = tmp_path / "file.pdf"
        local.write_bytes(b"data")

        with patch.object(drive, "_service") as mock_svc:
            svc = MagicMock()
            mock_svc.return_value = svc

            with patch.object(paths, "ensure_path", side_effect=_make_http_error(500)):
                with pytest.raises(NetworkError):
                    drive.upload(fake_cred, str(local), "/velmiren/file.pdf")


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------


class TestDownload:
    def test_downloads_to_file(self, tmp_path, fake_cred):
        dest = tmp_path / "notes.txt"
        dest.write_bytes(b"hello world")

        with patch.object(drive, "_service") as mock_svc:
            svc = MagicMock()
            mock_svc.return_value = svc

            with patch.object(paths, "resolve", return_value="file-id"):
                svc.files.return_value.get_media.return_value = MagicMock()
                with patch("velmiren.drive.MediaIoBaseDownload") as mock_dl:
                    instance = MagicMock()
                    instance.next_chunk.return_value = (None, True)
                    mock_dl.return_value = instance
                    result = drive.download(fake_cred, "/velmiren/notes.txt", str(dest))

        assert result == dest.stat().st_size

    def test_dir_target_uses_remote_name(self, tmp_path, fake_cred):
        dest_dir = tmp_path / "downloads"
        dest_dir.mkdir()
        expected = dest_dir / "notes.txt"
        expected.write_bytes(b"data")

        with patch.object(drive, "_service") as mock_svc:
            svc = MagicMock()
            mock_svc.return_value = svc

            with patch.object(paths, "resolve", return_value="file-id"):
                svc.files.return_value.get_media.return_value = MagicMock()
                with patch("velmiren.drive.MediaIoBaseDownload") as mock_dl:
                    instance = MagicMock()
                    instance.next_chunk.return_value = (None, True)
                    mock_dl.return_value = instance
                    drive.download(fake_cred, "/velmiren/notes.txt", str(dest_dir))

        assert expected.exists()

    def test_remote_not_found_propagates(self, tmp_path, fake_cred):
        with patch.object(drive, "_service"):
            with patch.object(paths, "resolve", side_effect=RemoteNotFoundError("no such remote file")):
                with pytest.raises(RemoteNotFoundError):
                    drive.download(fake_cred, "/velmiren/missing.txt", str(tmp_path / "out.txt"))

    def test_http_error_raises_network_error(self, tmp_path, fake_cred):
        with patch.object(drive, "_service") as mock_svc:
            svc = MagicMock()
            mock_svc.return_value = svc
            with patch.object(paths, "resolve", return_value="file-id"):
                svc.files.return_value.get_media.side_effect = _make_http_error(403)
                with pytest.raises(NetworkError):
                    drive.download(fake_cred, "/velmiren/file.txt", str(tmp_path / "out.txt"))


# ---------------------------------------------------------------------------
# list_dir
# ---------------------------------------------------------------------------


class TestListDir:
    def test_returns_files(self, fake_cred):
        with patch.object(drive, "_service") as mock_svc:
            svc = MagicMock()
            mock_svc.return_value = svc
            svc.files.return_value.list.return_value.execute.return_value = {
                "files": [
                    {"name": "a.txt", "size": "100", "modifiedTime": "2025-01-01T00:00:00.000Z", "id": "id1"}
                ]
            }
            result = drive.list_dir(fake_cred, "folder-id")

        assert len(result) == 1
        assert result[0]["name"] == "a.txt"

    def test_returns_empty_list_for_empty_folder(self, fake_cred):
        with patch.object(drive, "_service") as mock_svc:
            svc = MagicMock()
            mock_svc.return_value = svc
            svc.files.return_value.list.return_value.execute.return_value = {"files": []}
            result = drive.list_dir(fake_cred, "folder-id")

        assert result == []

    def test_http_error_raises_network_error(self, fake_cred):
        with patch.object(drive, "_service") as mock_svc:
            svc = MagicMock()
            mock_svc.return_value = svc
            svc.files.return_value.list.return_value.execute.side_effect = _make_http_error(500)
            with pytest.raises(NetworkError):
                drive.list_dir(fake_cred, "folder-id")


# ---------------------------------------------------------------------------
# file_exists
# ---------------------------------------------------------------------------


class TestFileExists:
    def test_returns_true_when_found(self, fake_cred):
        with patch.object(drive, "_service"):
            with patch.object(paths, "resolve", return_value="file-id"):
                assert drive.file_exists(fake_cred, "/velmiren/foo.pdf") is True

    def test_returns_false_when_not_found(self, fake_cred):
        with patch.object(drive, "_service"):
            with patch.object(paths, "resolve", side_effect=RemoteNotFoundError("no such remote file")):
                assert drive.file_exists(fake_cred, "/velmiren/missing.pdf") is False

    def test_http_error_raises_network_error(self, fake_cred):
        with patch.object(drive, "_service"):
            with patch.object(paths, "resolve", side_effect=_make_http_error(500)):
                with pytest.raises(NetworkError):
                    drive.file_exists(fake_cred, "/velmiren/file.pdf")


# ---------------------------------------------------------------------------
# delete_file
# ---------------------------------------------------------------------------


class TestDeleteFile:
    def test_deletes_successfully(self, fake_cred):
        with patch.object(drive, "_service") as mock_svc:
            svc = MagicMock()
            mock_svc.return_value = svc
            svc.files.return_value.delete.return_value.execute.return_value = None
            with patch.object(paths, "resolve", return_value="file-id"):
                drive.delete_file(fake_cred, "/velmiren/old.tmp")

        svc.files.return_value.delete.assert_called_once_with(fileId="file-id")

    def test_not_found_raises(self, fake_cred):
        with patch.object(drive, "_service"):
            with patch.object(paths, "resolve", side_effect=RemoteNotFoundError("no such remote file")):
                with pytest.raises(RemoteNotFoundError):
                    drive.delete_file(fake_cred, "/velmiren/missing.tmp")

    def test_http_error_raises_network_error(self, fake_cred):
        with patch.object(drive, "_service") as mock_svc:
            svc = MagicMock()
            mock_svc.return_value = svc
            with patch.object(paths, "resolve", return_value="file-id"):
                svc.files.return_value.delete.return_value.execute.side_effect = _make_http_error(403)
                with pytest.raises(NetworkError):
                    drive.delete_file(fake_cred, "/velmiren/file.tmp")
