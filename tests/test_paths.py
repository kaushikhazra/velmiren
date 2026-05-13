"""Tests for velmiren.paths — remote path resolution."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from velmiren import paths
from velmiren.errors import RemoteNotFoundError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_svc(responses: list):
    """
    Build a fake Drive service where each call to
    svc.files().list(...).execute() returns the next item in `responses`.
    """
    svc = MagicMock()
    execute_mock = MagicMock(side_effect=responses)
    svc.files.return_value.list.return_value.execute = execute_mock
    return svc


# ---------------------------------------------------------------------------
# _resolve_remote_root
# ---------------------------------------------------------------------------


class TestResolveRemoteRoot:
    def test_default_is_velmiren(self, monkeypatch):
        monkeypatch.delenv("VELMIREN_REMOTE_ROOT", raising=False)
        assert paths._resolve_remote_root() == "velmiren"

    def test_plain_name_override(self, monkeypatch):
        monkeypatch.setenv("VELMIREN_REMOTE_ROOT", "myroot")
        assert paths._resolve_remote_root() == "myroot"

    def test_id_prefix_strips_prefix(self, monkeypatch):
        monkeypatch.setenv("VELMIREN_REMOTE_ROOT", "id:1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms")
        result = paths._resolve_remote_root()
        assert result == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"


# ---------------------------------------------------------------------------
# resolve (happy path + cache)
# ---------------------------------------------------------------------------


class TestResolve:
    def setup_method(self):
        paths._cache.clear()

    def test_happy_path_single_segment(self, monkeypatch):
        monkeypatch.delenv("VELMIREN_REMOTE_ROOT", raising=False)
        # Walk: root-folder lookup → file lookup
        svc = _make_svc([
            {"files": [{"id": "folder-id"}]},  # "velmiren" under root
            {"files": [{"id": "file-id"}]},    # "foo.pdf" under folder-id
        ])
        result = paths.resolve(svc, "foo.pdf")
        assert result == "file-id"

    def test_cache_hit_avoids_api_call(self, monkeypatch):
        monkeypatch.delenv("VELMIREN_REMOTE_ROOT", raising=False)
        paths._cache["foo.pdf"] = "cached-id"
        svc = MagicMock()
        result = paths.resolve(svc, "foo.pdf")
        assert result == "cached-id"
        svc.files.assert_not_called()

    def test_missing_segment_raises(self, monkeypatch):
        monkeypatch.delenv("VELMIREN_REMOTE_ROOT", raising=False)
        svc = _make_svc([
            {"files": []},  # "velmiren" not found
        ])
        with pytest.raises(RemoteNotFoundError):
            paths.resolve(svc, "missing.pdf")

    def test_missing_leaf_raises(self, monkeypatch):
        monkeypatch.delenv("VELMIREN_REMOTE_ROOT", raising=False)
        svc = _make_svc([
            {"files": [{"id": "folder-id"}]},  # "velmiren" found
            {"files": []},                      # leaf not found
        ])
        with pytest.raises(RemoteNotFoundError):
            paths.resolve(svc, "nothere.txt")

    def test_id_prefix_root(self, monkeypatch):
        monkeypatch.setenv("VELMIREN_REMOTE_ROOT", "id:ROOT123")
        svc = _make_svc([
            {"files": [{"id": "file-id"}]},  # direct child of ROOT123
        ])
        result = paths.resolve(svc, "foo.pdf")
        assert result == "file-id"


# ---------------------------------------------------------------------------
# ensure_path
# ---------------------------------------------------------------------------


class TestEnsurePath:
    def setup_method(self):
        paths._cache.clear()

    def test_creates_missing_folder(self, monkeypatch):
        monkeypatch.delenv("VELMIREN_REMOTE_ROOT", raising=False)
        svc = MagicMock()
        # For "velmiren" lookup: not found → created
        svc.files.return_value.list.return_value.execute.return_value = {"files": []}
        svc.files.return_value.create.return_value.execute.return_value = {"id": "new-folder-id"}

        parent_id, name = paths.ensure_path(svc, "velmiren/report.pdf")
        assert name == "report.pdf"

    def test_reuses_existing_folder(self, monkeypatch):
        monkeypatch.delenv("VELMIREN_REMOTE_ROOT", raising=False)
        svc = MagicMock()
        svc.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "existing-folder"}]
        }
        parent_id, name = paths.ensure_path(svc, "velmiren/report.pdf")
        assert name == "report.pdf"
        # No create call should have been made
        svc.files.return_value.create.assert_not_called()

    def test_deep_path_creates_all_folders(self, monkeypatch):
        monkeypatch.delenv("VELMIREN_REMOTE_ROOT", raising=False)
        svc = MagicMock()
        # All folder lookups return not-found; creates return sequential IDs
        svc.files.return_value.list.return_value.execute.return_value = {"files": []}
        create_responses = [{"id": f"id-{i}"} for i in range(5)]
        svc.files.return_value.create.return_value.execute.side_effect = create_responses

        parent_id, name = paths.ensure_path(svc, "a/b/c/file.txt")
        assert name == "file.txt"
