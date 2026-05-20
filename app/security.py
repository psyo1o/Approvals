"""세션 유휴 만료·IP 허용 목록 미들웨어 (Phase 6.1)."""
from __future__ import annotations

import fnmatch
import ipaddress
import os
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from itsdangerous import BadSignature, URLSafeSerializer
from starlette.middleware.base import BaseHTTPMiddleware

APP_SECRET = os.getenv("APP_SECRET", "change-me-long-random")
signer = URLSafeSerializer(APP_SECRET, salt="approval_mvp_session")

SESSION_IDLE_SECONDS = int(os.getenv("SESSION_IDLE_SECONDS", "7200"))
SESSION_ABSOLUTE_SECONDS = int(os.getenv("SESSION_ABSOLUTE_SECONDS", str(3600 * 24 * 30)))
TRUST_PROXY = os.getenv("TRUST_PROXY", "").strip().lower() in ("1", "true", "yes", "on")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _activity_iso(dt: Optional[datetime] = None) -> str:
    t = dt or _utc_now()
    return t.isoformat()


def create_session_payload(uid: int, last_activity: Optional[str] = None) -> dict[str, Any]:
    return {"uid": int(uid), "last_activity": last_activity or _activity_iso()}


def create_session_token(uid: int) -> str:
    return signer.dumps(create_session_payload(uid))


def load_session_token(token: str) -> dict[str, Any]:
    """절대 만료(max_age) 검증 후 payload 반환."""
    data = signer.loads(token, max_age=SESSION_ABSOLUTE_SECONDS)
    if not isinstance(data, dict):
        raise BadSignature("invalid session shape")
    return data


def session_idle_expired(data: dict[str, Any]) -> bool:
    raw = data.get("last_activity")
    if not raw:
        return False
    try:
        s = str(raw).replace("Z", "+00:00")
        last = datetime.fromisoformat(s)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return False
    elapsed = (_utc_now() - last).total_seconds()
    return elapsed > SESSION_IDLE_SECONDS


def refresh_session_token(data: dict[str, Any]) -> str:
    uid = int(data.get("uid", 0))
    return signer.dumps(create_session_payload(uid, _activity_iso()))


def _parse_allowed_ips(raw: str) -> list[str]:
    return [p.strip() for p in raw.split(",") if p.strip()]


def _client_ip(request: Request) -> str:
    if TRUST_PROXY:
        xff = (request.headers.get("x-forwarded-for") or "").strip()
        if xff:
            return xff.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return ""


def ip_allowed(client_ip: str, patterns: list[str]) -> bool:
    if not patterns:
        return True
    if not client_ip:
        return False
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        addr = None
    for pattern in patterns:
        p = pattern.strip()
        if not p:
            continue
        if "*" in p and fnmatch.fnmatchcase(client_ip, p):
            return True
        if "/" in p and addr is not None:
            try:
                if addr in ipaddress.ip_network(p, strict=False):
                    return True
            except ValueError:
                pass
        if client_ip == p:
            return True
    return False


def _should_skip_security(path: str) -> bool:
    if path == "/login":
        return True
    if path.startswith("/static"):
        return True
    if path == "/favicon.ico":
        return True
    return False


class IpAllowlistMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, allowed_ips: Optional[str] = None) -> None:
        super().__init__(app)
        raw = allowed_ips if allowed_ips is not None else os.getenv("ALLOWED_IPS", "")
        self._patterns = _parse_allowed_ips(raw)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self._patterns:
            return await call_next(request)
        client_ip = _client_ip(request)
        if ip_allowed(client_ip, self._patterns):
            return await call_next(request)
        return PlainTextResponse("허용되지 않은 IP에서의 접근입니다.", status_code=403)


class SessionIdleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if _should_skip_security(path):
            return await call_next(request)

        token = request.cookies.get("session")
        if not token:
            return await call_next(request)

        try:
            data = load_session_token(token)
        except BadSignature:
            if path.startswith("/api/"):
                resp = JSONResponse({"detail": "세션이 유효하지 않습니다."}, status_code=401)
            else:
                resp = RedirectResponse(url="/login?reason=invalid_session", status_code=303)
            resp.delete_cookie("session")
            return resp

        if session_idle_expired(data):
            if path.startswith("/api/"):
                resp = JSONResponse({"detail": "세션이 만료되었습니다. 다시 로그인해 주세요."}, status_code=401)
            else:
                resp = RedirectResponse(url="/login?reason=session_expired", status_code=303)
            resp.delete_cookie("session")
            return resp

        response = await call_next(request)
        try:
            new_token = refresh_session_token(data)
            response.set_cookie(
                "session",
                new_token,
                httponly=True,
                samesite="lax",
                max_age=SESSION_ABSOLUTE_SECONDS,
            )
        except Exception:
            pass
        return response
