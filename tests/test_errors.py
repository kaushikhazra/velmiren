"""Tests for velmiren.errors — exception hierarchy and exit codes."""

import pytest

from velmiren.errors import (
    EXIT_AUTH,
    EXIT_NETWORK,
    EXIT_NOT_FOUND,
    EXIT_SUCCESS,
    EXIT_USER,
    AuthExpiredError,
    NetworkError,
    NotAuthenticatedError,
    RemoteNotFoundError,
    UserError,
    VelmirenError,
)


class TestExitCodeConstants:
    def test_success_is_zero(self):
        assert EXIT_SUCCESS == 0

    def test_not_found_is_one(self):
        assert EXIT_NOT_FOUND == 1

    def test_auth_is_two(self):
        assert EXIT_AUTH == 2

    def test_user_is_three(self):
        assert EXIT_USER == 3

    def test_network_is_four(self):
        assert EXIT_NETWORK == 4


class TestVelmirenError:
    def test_is_exception(self):
        err = VelmirenError("test")
        assert isinstance(err, Exception)

    def test_message_stored(self):
        err = VelmirenError("hello")
        assert err.message == "hello"

    def test_default_message_empty(self):
        err = VelmirenError()
        assert err.message == ""

    def test_exit_code_default(self):
        assert VelmirenError.exit_code == 1


class TestNotAuthenticatedError:
    def test_exit_code(self):
        assert NotAuthenticatedError.exit_code == 2

    def test_default_message(self):
        err = NotAuthenticatedError()
        assert "not authenticated" in err.message
        assert "velmiren auth google" in err.message

    def test_is_velmiren_error(self):
        assert isinstance(NotAuthenticatedError(), VelmirenError)


class TestAuthExpiredError:
    def test_exit_code(self):
        assert AuthExpiredError.exit_code == 2

    def test_default_message(self):
        err = AuthExpiredError()
        assert "expired" in err.message

    def test_custom_message(self):
        err = AuthExpiredError("custom msg")
        assert err.message == "custom msg"


class TestRemoteNotFoundError:
    def test_exit_code(self):
        assert RemoteNotFoundError.exit_code == 1

    def test_custom_message(self):
        err = RemoteNotFoundError("no such remote file")
        assert err.message == "no such remote file"


class TestUserError:
    def test_exit_code(self):
        assert UserError.exit_code == 3

    def test_custom_message(self):
        err = UserError("--force required")
        assert err.message == "--force required"


class TestNetworkError:
    def test_exit_code(self):
        assert NetworkError.exit_code == 4

    def test_custom_message(self):
        err = NetworkError("timeout")
        assert err.message == "timeout"

    def test_status_code_kwarg(self):
        err = NetworkError("forbidden", status_code=403)
        assert err.status_code == 403

    def test_status_code_default_none(self):
        err = NetworkError("oops")
        assert err.status_code is None


