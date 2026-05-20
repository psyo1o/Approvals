"""부재중 자동 대결 (Phase 6.3)."""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional, Sequence, Set, Type

from sqlalchemy.orm import Session

MAX_DELEGATION_DEPTH = 3


def today_for_leave() -> date:
    """컨테이너 TZ(Asia/Seoul) 기준 오늘 날짜."""
    return date.today()


def is_user_on_leave_today(
    db: Session,
    user_id: int,
    schedule_cls: Type[Any],
    on_date: Optional[date] = None,
) -> bool:
    today_str = (on_date or today_for_leave()).isoformat()
    row = (
        db.query(schedule_cls.id)
        .filter(
            schedule_cls.user_id == user_id,
            schedule_cls.schedule_type == "LEAVE",
            schedule_cls.status == "ACTIVE",
            schedule_cls.start_date <= today_str,
            schedule_cls.end_date >= today_str,
        )
        .first()
    )
    return row is not None


def resolve_effective_approver_id(
    db: Session,
    user_id: int,
    user_cls: Type[Any],
    schedule_cls: Type[Any],
    on_date: Optional[date] = None,
    *,
    depth: int = 0,
    visited: Optional[Set[int]] = None,
) -> int:
    """휴가 중이면 delegate_id를 따라 최대 MAX_DELEGATION_DEPTH까지 위임."""
    if depth >= MAX_DELEGATION_DEPTH:
        return int(user_id)
    seen = visited if visited is not None else set()
    uid = int(user_id)
    if uid in seen:
        return uid
    seen.add(uid)

    if not is_user_on_leave_today(db, uid, schedule_cls, on_date):
        return uid

    user = db.get(user_cls, uid)
    if not user:
        return uid
    # 대결자 미지정 시 자동 위임 없음 → 원 결재자가 그대로 결재
    delegate_id = getattr(user, "delegate_id", None)
    if not delegate_id:
        return uid
    delegate = db.get(user_cls, int(delegate_id))
    if not delegate or not bool(getattr(delegate, "is_active", True)):
        return uid
    return resolve_effective_approver_id(
        db,
        int(delegate.id),
        user_cls,
        schedule_cls,
        on_date,
        depth=depth + 1,
        visited=seen,
    )


def apply_auto_delegation_for_approver(
    db: Session,
    approver_row: Any,
    *,
    doc_id: int,
    doc_title: str,
    doc_link: str,
    user_cls: Type[Any],
    schedule_cls: Type[Any],
    event_log_cls: Type[Any],
    notify: Optional[Callable[[Session, int, str, str], None]] = None,
    on_date: Optional[date] = None,
) -> bool:
    """
    결재자가 오늘 휴가이고 대결자가 있으면 approver_id를 갱신.
    최초 위임 시 original_approver_id에 원 결재자를 보관.
    """
    nominal_id = int(getattr(approver_row, "original_approver_id", None) or approver_row.approver_id)
    effective_id = resolve_effective_approver_id(
        db, nominal_id, user_cls, schedule_cls, on_date
    )
    current_id = int(approver_row.approver_id)
    if effective_id == current_id:
        return False

    absent_user = db.get(user_cls, nominal_id)
    delegate_user = db.get(user_cls, effective_id)
    absent_name = (absent_user.name if absent_user else str(nominal_id)) or str(nominal_id)
    delegate_name = (delegate_user.name if delegate_user else str(effective_id)) or str(effective_id)

    if getattr(approver_row, "original_approver_id", None) is None:
        approver_row.original_approver_id = nominal_id
    approver_row.approver_id = effective_id

    db.add(
        event_log_cls(
            doc_id=doc_id,
            user_id=effective_id,
            event="AUTO_DELEGATE",
            note=f"{absent_name}님 부재(휴가)로 {delegate_name}님에게 자동 대결 지정",
        )
    )
    if notify:
        title = f"[대결지정] {absent_name}님의 부재로 「{doc_title}」 결재가 대결 지정되었습니다"
        notify(db, effective_id, title, doc_link)
    return True


def apply_auto_delegation_for_rows(
    db: Session,
    approver_rows: Sequence[Any],
    *,
    doc_id: int,
    doc_title: str,
    doc_link: str,
    user_cls: Type[Any],
    schedule_cls: Type[Any],
    event_log_cls: Type[Any],
    notify: Optional[Callable[[Session, int, str, str], None]] = None,
    actions: Optional[Sequence[str]] = None,
    on_date: Optional[date] = None,
) -> int:
    """여러 결재 행에 대해 자동 대결 적용. 변경 건수 반환."""
    allowed = set(actions) if actions is not None else {"PENDING", "WAITING"}
    count = 0
    for row in approver_rows:
        if str(getattr(row, "action", "")) not in allowed:
            continue
        if apply_auto_delegation_for_approver(
            db,
            row,
            doc_id=doc_id,
            doc_title=doc_title,
            doc_link=doc_link,
            user_cls=user_cls,
            schedule_cls=schedule_cls,
            event_log_cls=event_log_cls,
            notify=notify,
            on_date=on_date,
        ):
            count += 1
    return count
