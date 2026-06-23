"""상단 메뉴 탭 표시 설정 (관리자 전용 구성)."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from database import Base

NAV_SETTINGS_KEY = "nav_visibility"

# paths: 해당 탭과 연결된 URL 접두사 (긴 경로 우선 매칭)
NAV_ITEMS: List[Dict[str, Any]] = [
    {"key": "search", "label": "검색", "group": "core", "paths": ("/search",)},
    {"key": "documents", "label": "문서", "group": "core", "paths": ("/dashboard", "/doc")},
    {"key": "completed", "label": "완료", "group": "core", "paths": ("/completed",)},
    {
        "key": "accounting_dashboard",
        "label": "일월계표",
        "group": "core",
        "paths": ("/accounting/dashboard",),
    },
    {
        "key": "accounting_ledger",
        "label": "미수금",
        "group": "core",
        "paths": ("/accounting/ledger",),
    },
    {"key": "boards", "label": "게시판", "group": "collab", "paths": ("/boards", "/board")},
    {"key": "messages", "label": "쪽지", "group": "collab", "paths": ("/messages", "/message")},
    {"key": "org", "label": "조직도", "group": "collab", "paths": ("/org",)},
    {"key": "quality", "label": "품질", "group": "collab", "paths": ("/quality",)},
    {"key": "calendar", "label": "일정", "group": "collab", "paths": ("/calendar",)},
    {"key": "work_schedule", "label": "근무표", "group": "collab", "paths": ("/work-schedule",)},
    {"key": "leave", "label": "휴가", "group": "collab", "paths": ("/leave",)},
    {"key": "me", "label": "내정보", "group": "collab", "paths": ("/me",)},
]

NAV_PATH_RULES: List[Tuple[str, str]] = []
for _item in NAV_ITEMS:
    for _path in _item["paths"]:
        NAV_PATH_RULES.append((_path, _item["key"]))
NAV_PATH_RULES.sort(key=lambda x: len(x[0]), reverse=True)

NAV_ALWAYS_ALLOWED_PREFIXES = (
    "/login",
    "/logout",
    "/static",
    "/admin",
    "/api",
    "/change-password",
    "/notifications",
    "/branch-view",
    "/favicon",
)


class AppSetting(Base):
    __tablename__ = "app_settings"
    id = Column(Integer, primary_key=True)
    key = Column(String(80), unique=True, nullable=False)
    value = Column(Text, nullable=False, default="{}")


def default_nav_visibility() -> Dict[str, bool]:
    return {item["key"]: True for item in NAV_ITEMS}


def _merge_visibility(raw: Optional[Dict[str, Any]]) -> Dict[str, bool]:
    out = default_nav_visibility()
    if not raw:
        return out
    for item in NAV_ITEMS:
        key = item["key"]
        if key in raw:
            out[key] = bool(raw[key])
    return out


def get_nav_visibility(db: Session) -> Dict[str, bool]:
    row = db.query(AppSetting).filter(AppSetting.key == NAV_SETTINGS_KEY).first()
    if not row or not (row.value or "").strip():
        return default_nav_visibility()
    try:
        data = json.loads(row.value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default_nav_visibility()
    if not isinstance(data, dict):
        return default_nav_visibility()
    return _merge_visibility(data)


def save_nav_visibility(db: Session, values: Dict[str, bool]) -> Dict[str, bool]:
    merged = _merge_visibility(values)
    payload = json.dumps(merged, ensure_ascii=False)
    row = db.query(AppSetting).filter(AppSetting.key == NAV_SETTINGS_KEY).first()
    if row:
        row.value = payload
    else:
        db.add(AppSetting(key=NAV_SETTINGS_KEY, value=payload))
    db.commit()
    return merged


def nav_visibility_for_user(db: Session, user: Any) -> Dict[str, bool]:
    if user and bool(getattr(user, "is_admin", False)):
        return default_nav_visibility()
    return get_nav_visibility(db)


def nav_key_for_path(path: str) -> Optional[str]:
    for prefix, key in NAV_PATH_RULES:
        if path == prefix or path.startswith(prefix + "/"):
            return key
    return None


def is_nav_path_allowed(path: str, visibility: Dict[str, bool]) -> bool:
    if any(path == p or path.startswith(p + "/") for p in NAV_ALWAYS_ALLOWED_PREFIXES):
        return True
    key = nav_key_for_path(path)
    if key is None:
        return True
    return bool(visibility.get(key, True))


class NavAccessMiddleware(BaseHTTPMiddleware):
    """비관리자가 숨긴 메뉴 URL에 직접 접근하지 못하도록 차단."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path or "/"
        if request.method not in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"):
            return await call_next(request)
        if any(path == p or path.startswith(p + "/") for p in NAV_ALWAYS_ALLOWED_PREFIXES):
            return await call_next(request)

        load_session = getattr(request.app.state, "nav_load_session", None)
        if not load_session:
            return await call_next(request)
        user_model = request.app.state.nav_user_model
        db_factory = request.app.state.nav_db_factory

        token = request.cookies.get("session")
        if not token:
            return await call_next(request)

        db = db_factory()
        try:
            try:
                data = load_session(token)
            except Exception:
                return await call_next(request)
            uid = int(data.get("uid") or 0)
            if uid <= 0:
                return await call_next(request)
            user = db.query(user_model).filter(user_model.id == uid).first()
            if not user or not bool(getattr(user, "is_active", True)):
                return await call_next(request)
            if bool(getattr(user, "is_admin", False)):
                return await call_next(request)
            visibility = get_nav_visibility(db)
            if is_nav_path_allowed(path, visibility):
                return await call_next(request)
            if request.headers.get("accept", "").find("application/json") >= 0:
                from fastapi.responses import JSONResponse

                return JSONResponse({"detail": "이 메뉴는 현재 사용할 수 없습니다."}, status_code=403)
            return RedirectResponse(
                url="/dashboard?flash=" + quote("접근할 수 없는 메뉴입니다.", safe=""),
                status_code=303,
            )
        finally:
            db.close()
