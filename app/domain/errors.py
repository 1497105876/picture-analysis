"""领域错误（API 层统一映射为错误码 + 中文人话 message）。"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    code = "INTERNAL_ERROR"
    status = 500

    def __init__(self, message: str, **detail: Any) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class ValidationAppError(AppError):
    code = "VALIDATION_ERROR"
    status = 422


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status = 404


class ConflictError(AppError):
    code = "CONFLICT"
    status = 409


class DirNotFoundError(AppError):
    code = "DIR_NOT_FOUND"
    status = 404


class DirAlreadyRegistered(AppError):
    code = "DIR_ALREADY_REGISTERED"
    status = 409


class RateLimited(AppError):
    code = "RATE_LIMITED"
    status = 429


class DailyBudgetExceeded(AppError):
    code = "DAILY_BUDGET_EXCEEDED"
    status = 429


class AiUnavailable(AppError):
    code = "AI_SERVICE_UNAVAILABLE"
    status = 503


class ConfirmWordMismatch(AppError):
    code = "CONFIRM_WORD_MISMATCH"
    status = 400


class HiddenNotBypassable(AppError):
    code = "HIDDEN_NOT_BYPASSABLE"
    status = 400


class PathTraversalError(AppError):
    code = "PATH_TRAVERSAL"
    status = 400
