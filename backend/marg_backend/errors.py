"""Structured API errors.

Every error response has the shape::

    {"error": {"code": "<machine_code>", "message": "<human text>", "details": [...]?}}

Messages never echo request payload contents or secrets.
"""
from __future__ import annotations

from typing import Any, Optional


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[Any] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers

    def body(self) -> dict:
        err: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            err["details"] = self.details
        return {"error": err}


def unauthorized(message: str = "Missing or invalid credentials.") -> ApiError:
    return ApiError(
        401, "unauthorized", message, headers={"WWW-Authenticate": "Bearer"}
    )


def forbidden(code: str = "forbidden", message: str = "Access denied.") -> ApiError:
    return ApiError(403, code, message)


def not_found(message: str = "Resource not found.") -> ApiError:
    return ApiError(404, "not_found", message)
