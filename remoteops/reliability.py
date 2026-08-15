import json
import logging
import math
import re
import threading
import time
from collections.abc import Callable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
request_logger = logging.getLogger("remoteops.requests")


class FixedWindowRateLimiter:
    """Limit requests per key during a fixed time window."""

    def __init__(
        self,
        limit: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> int | None:
        """Return retry seconds when the key has exceeded its allowance."""
        now = self._clock()
        with self._lock:
            self._windows = {
                stored_key: window
                for stored_key, window in self._windows.items()
                if now - window[0] < self.window_seconds
            }
            started_at, count = self._windows.get(key, (now, 0))
            if count >= self.limit:
                return max(1, math.ceil(self.window_seconds - (now - started_at)))
            self._windows[key] = (started_at, count + 1)
        return None

    def clear(self) -> None:
        """Clear counters, primarily to isolate tests."""
        with self._lock:
            self._windows.clear()


def error_response(
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build the API's standard error response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
            }
        },
        headers=headers,
    )


def is_rate_limited_path(path: str) -> bool:
    """Identify public authentication endpoints vulnerable to abuse."""
    return path.startswith("/auth/") or path == "/users/register"


def configure_reliability(
    app: FastAPI, rate_limit: int, rate_window_seconds: int
) -> None:
    """Install request tracing, logging, errors, and auth rate limiting."""
    # ponytail: counters are per process; use Redis when the API runs multiple workers.
    limiter = FixedWindowRateLimiter(rate_limit, rate_window_seconds)
    app.state.auth_rate_limiter = limiter

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable) -> Response:
        supplied_id = request.headers.get("X-Request-ID", "")
        request_id = (
            supplied_id if REQUEST_ID_PATTERN.fullmatch(supplied_id) else str(uuid4())
        )
        request.state.request_id = request_id
        started_at = time.perf_counter()

        response = None
        if is_rate_limited_path(request.url.path):
            client = request.client.host if request.client else "unknown"
            retry_after = limiter.check(f"{client}:{request.url.path}")
            if retry_after is not None:
                response = error_response(
                    429,
                    "rate_limit_exceeded",
                    "Too many requests",
                    request_id,
                    {"Retry-After": str(retry_after)},
                )
        if response is None:
            try:
                response = await call_next(request)
            except Exception:
                logging.getLogger("remoteops.errors").exception(
                    "Unhandled request error", extra={"request_id": request_id}
                )
                response = error_response(
                    500,
                    "internal_error",
                    "Internal server error",
                    request_id,
                )

        response.headers["X-Request-ID"] = request_id
        request_logger.info(
            json.dumps(
                {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round(
                        (time.perf_counter() - started_at) * 1000, 2
                    ),
                    "request_id": request_id,
                },
                separators=(",", ":"),
            )
        )
        return response

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exception: HTTPException
    ) -> JSONResponse:
        if exception.status_code >= 500:
            message = (
                "Service unavailable"
                if exception.status_code == 503
                else "Internal server error"
            )
        else:
            message = (
                exception.detail
                if isinstance(exception.detail, str)
                else "Request failed"
            )
        return error_response(
            exception.status_code,
            "http_error",
            message,
            request.state.request_id,
            exception.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exception: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            422,
            "validation_error",
            "Request validation failed",
            request.state.request_id,
        )

    @app.exception_handler(Exception)
    async def unexpected_exception_handler(
        request: Request, exception: Exception
    ) -> JSONResponse:
        logging.getLogger("remoteops.errors").exception(
            "Unhandled request error", extra={"request_id": request.state.request_id}
        )
        return error_response(
            500,
            "internal_error",
            "Internal server error",
            request.state.request_id,
        )
