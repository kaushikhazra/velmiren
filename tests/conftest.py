"""Shared pytest fixtures for Velmiren tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def fake_drive_service():
    """MagicMock shaped like the Drive v3 service object."""
    svc = MagicMock()
    files = MagicMock()
    svc.files.return_value = files
    return svc


@pytest.fixture
def fake_cred():
    """Minimal cred object that passes auth.load() checks."""
    cred = MagicMock()
    cred.token = "fake-access-token"
    cred.valid = True
    cred.expired = False
    cred.expiry = None
    return cred


@pytest.fixture
def fake_cred_data():
    """Plain dict with all six cred-file fields populated with test placeholders."""
    return {
        "refresh_token": "test-refresh-token",
        "client_id": "test-client-id.apps.googleusercontent.com",
        "client_secret": "test-client-secret",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/drive.file openid email",
        "email": "test@example.com",
    }
