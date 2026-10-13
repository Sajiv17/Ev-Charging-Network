"""Business errors. main.py turns these into JSON: {"detail": ..., "code": ...}."""


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class SlotUnavailable(Conflict):
    code = "slot_unavailable"


class InsufficientBalance(AppError):
    status_code = 402
    code = "insufficient_balance"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


class NotImplementedYet(AppError):
    status_code = 501
    code = "not_implemented"
