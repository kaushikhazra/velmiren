"""
Velmiren exception hierarchy and exit-code constants.
"""

# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

EXIT_SUCCESS = 0
EXIT_NOT_FOUND = 1
EXIT_AUTH = 2
EXIT_USER = 3
EXIT_NETWORK = 4
EXIT_SIZE_CAP = 5


# ---------------------------------------------------------------------------
# Base exception
# ---------------------------------------------------------------------------


class VelmirenError(Exception):
    exit_code: int = 1
    message: str = ""

    def __init__(self, message: str = "") -> None:
        self.message = message or self.__class__.message
        super().__init__(self.message)


# ---------------------------------------------------------------------------
# Subclasses
# ---------------------------------------------------------------------------


class NotAuthenticatedError(VelmirenError):
    exit_code = EXIT_AUTH
    message = "not authenticated — run 'velmiren auth google' first"


class AuthExpiredError(VelmirenError):
    exit_code = EXIT_AUTH
    message = "authentication expired — run 'velmiren auth google' to re-authenticate"


class RemoteNotFoundError(VelmirenError):
    exit_code = EXIT_NOT_FOUND
    # message supplied at raise site: "no such remote file" or "no such remote folder"


class UserError(VelmirenError):
    exit_code = EXIT_USER
    # message supplied at raise site


class NetworkError(VelmirenError):
    exit_code = EXIT_NETWORK

    def __init__(self, message: str = "", status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class SizeCapError(VelmirenError):
    exit_code = EXIT_SIZE_CAP
    message = "file exceeds v1 size cap (500 MB)"
