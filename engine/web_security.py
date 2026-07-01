"""HTTP hardening utilities for the public CurriculumAdvisor service.

The middleware in this module deliberately avoids logging query strings or
request bodies because transcript and simulation payloads may contain student
records.  The deployment currently uses one web process; the in-memory rate
limiter is therefore a useful first boundary.  A multi-instance deployment
should replace it with a shared limiter at the edge or in Redis.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

LOGGER = logging.getLogger("curriculum_advisor.http")


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject declared request bodies that exceed endpoint-specific limits.

    The PDF endpoint also enforces a streaming byte limit while reading the
    upload, so chunked requests cannot bypass the application-level limit.
    JSON/text endpoints additionally enforce bounded collections and strings.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        upload_limit_bytes: int,
        upload_limit_detail: str | None = None,
        json_limit_bytes: int,
    ) -> None:
        super().__init__(app)
        self.upload_limit_bytes = upload_limit_bytes
        self.upload_limit_detail = upload_limit_detail or "Request body exceeds the permitted size."
        self.json_limit_bytes = json_limit_bytes

    async def dispatch(self, request: Request, call_next):
        if request.method not in {"POST", "PUT", "PATCH"}:
            return await call_next(request)

        raw_length = request.headers.get("content-length")
        if not raw_length:
            return await call_next(request)
        try:
            declared_length = int(raw_length)
        except ValueError:
            return JSONResponse(
                {"detail": "Invalid Content-Length header."},
                status_code=400,
            )

        limit = (
            self.upload_limit_bytes
            if request.url.path == "/analyse"
            else self.json_limit_bytes
        )
        if declared_length > limit:
            detail = (
                self.upload_limit_detail
                if request.url.path == "/analyse"
                else "Request body exceeds the permitted size."
            )
            return JSONResponse(
                {"detail": detail},
                status_code=413,
            )
        return await call_next(request)


class SlidingWindowRateLimitMiddleware(BaseHTTPMiddleware):
    """Apply a small per-client sliding-window limit to analysis endpoints."""

    PROTECTED_PREFIXES = ("/analyse", "/simulate", "/goals")

    def __init__(
        self,
        app: ASGIApp,
        *,
        requests_per_window: int = 30,
        window_seconds: int = 60,
    ) -> None:
        super().__init__(app)
        self.requests_per_window = max(1, requests_per_window)
        self.window_seconds = max(1, window_seconds)
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @staticmethod
    def _client_key(request: Request) -> str:
        # Uvicorn's proxy-header handling should resolve the original client in
        # production.  Do not consume arbitrary X-Forwarded-For values here.
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        if (
            request.method == "OPTIONS"
            or request.method == "GET"
            or not request.url.path.startswith(self.PROTECTED_PREFIXES)
            or os.environ.get("RATE_LIMIT_ENABLED", "true").lower() == "false"
        ):
            return await call_next(request)

        now = time.monotonic()
        key = f"{self._client_key(request)}:analysis"
        with self._lock:
            events = self._events[key]
            cutoff = now - self.window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.requests_per_window:
                retry_after = max(1, int(self.window_seconds - (now - events[0])))
                return JSONResponse(
                    {
                        "detail": (
                            "Too many analysis requests. Please wait briefly "
                            "before trying again."
                        )
                    },
                    status_code=429,
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(self.requests_per_window),
                        "X-RateLimit-Remaining": "0",
                    },
                )
            events.append(now)
            remaining = max(0, self.requests_per_window - len(events))

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_window)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


class SecurityAndObservabilityMiddleware(BaseHTTPMiddleware):
    """Add browser security headers and privacy-preserving request metrics."""

    CONTENT_SECURITY_POLICY = "; ".join(
        (
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data:",
            "font-src 'self'",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
            "upgrade-insecure-requests",
        )
    )

    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            LOGGER.exception(
                "request_failed request_id=%s method=%s path=%s duration_ms=%.1f",
                request_id,
                request.method,
                request.url.path,
                duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - started) * 1000
        response.headers.setdefault("X-Request-ID", request_id)
        response.headers.setdefault("Content-Security-Policy", self.CONTENT_SECURITY_POLICY)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")

        forwarded_proto = request.headers.get("x-forwarded-proto", "")
        if request.url.scheme == "https" or forwarded_proto == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )

        if request.url.path.startswith(("/analyse", "/simulate", "/goals")):
            response.headers["Cache-Control"] = "no-store"

        LOGGER.info(
            "request_complete request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
