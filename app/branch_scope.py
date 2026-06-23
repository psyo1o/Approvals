"""Phase 7 — 지사(Branch) 논리적 격리 헬퍼."""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, List, Optional, Sequence, Set, Type

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session, joinedload

DEFAULT_BRANCH_ID = 1
CROSS_BRANCH_REP_GRADE_NAME = (os.getenv("CROSS_BRANCH_REP_GRADE_NAME") or "대표").strip()
VIEW_BRANCH_COOKIE = "view_branch_id"


def default_branch_id() -> int:
    return DEFAULT_BRANCH_ID


def user_branch_id(user: Any) -> int:
    bid = getattr(user, "branch_id", None)
    return int(bid) if bid is not None else DEFAULT_BRANCH_ID


def is_global_view(user: Any) -> bool:
    """레거시: 지사 전환 도입 후 문서 목록에는 사용하지 않음."""
    return bool(getattr(user, "is_admin", False))


def is_headquarters_branch_user(
    db: Session,
    user: Any,
    *,
    branch_cls: Optional[Type[Any]] = None,
) -> bool:
    """원주본사(WJ, is_headquarters) 소속 여부. 제천 지사 대표는 False."""
    bid = user_branch_id(user)
    if branch_cls is not None:
        br = db.query(branch_cls).filter(branch_cls.id == bid).first()
        if br is not None:
            return bool(getattr(br, "is_headquarters", False))
    return bid == DEFAULT_BRANCH_ID


def can_switch_branch_view(
    db: Session,
    user: Any,
    *,
    grade_cls: Type[Any],
    branch_cls: Optional[Type[Any]] = None,
) -> bool:
    """관리자, 또는 원주본사 소속 대표(및 그 위) — 조회 지사 전환. 제천 대표 제외."""
    if bool(getattr(user, "is_admin", False)):
        return True
    if not is_headquarters_branch_user(db, user, branch_cls=branch_cls):
        return False
    return is_cross_branch_approver_grade(db, grade_cls, getattr(user, "grade", "") or "")


def _parse_branch_id(raw: Any) -> Optional[int]:
    try:
        v = int(str(raw or "").strip())
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def resolve_view_branch_id(
    request: Any,
    user: Any,
    db: Session,
    *,
    grade_cls: Type[Any],
    branch_cls: Type[Any],
) -> int:
    """쿠키·쿼리 view_branch_id → 없으면 소속 지사."""
    home = user_branch_id(user)
    if not can_switch_branch_view(db, user, grade_cls=grade_cls, branch_cls=branch_cls):
        return home
    qp = getattr(request, "query_params", None)
    ck = getattr(request, "cookies", None)
    for raw in (
        qp.get("branch_id") if qp is not None else None,
        ck.get(VIEW_BRANCH_COOKIE) if ck is not None else None,
    ):
        bid = _parse_branch_id(raw)
        if bid and db.query(branch_cls).filter(branch_cls.id == bid).first():
            return bid
    return home


def cross_branch_grade_threshold(db: Session, grade_cls: Type[Any]) -> Optional[int]:
    """「대표」 직급의 sort_order(level). 이보다 작거나 같으면 전 지사 결재 후보."""
    rep = (
        db.query(grade_cls)
        .filter(grade_cls.name == CROSS_BRANCH_REP_GRADE_NAME, grade_cls.is_active == True)
        .first()
    )
    if not rep:
        return None
    return int(getattr(rep, "sort_order", None) or getattr(rep, "level", 99999))


def grade_sort_order(db: Session, grade_cls: Type[Any], grade_name: str) -> int:
    name = (grade_name or "").strip()
    if not name:
        return 99999
    g = db.query(grade_cls).filter(grade_cls.name == name).first()
    if g:
        return int(getattr(g, "sort_order", None) or getattr(g, "level", 99999))
    return 99999


def is_cross_branch_approver_grade(db: Session, grade_cls: Type[Any], grade_name: str) -> bool:
    threshold = cross_branch_grade_threshold(db, grade_cls)
    if threshold is None:
        return False
    return grade_sort_order(db, grade_cls, grade_name) <= threshold


def approver_candidate_ids(
    db: Session,
    user: Any,
    *,
    user_cls: Type[Any],
    grade_cls: Type[Any],
    exclude_user_id: Optional[int] = None,
) -> List[int]:
    """동일 지사 + 대표 및 그 위 직급(전 지사)."""
    my_branch = user_branch_id(user)
    threshold = cross_branch_grade_threshold(db, grade_cls)
    q = db.query(user_cls).filter(user_cls.is_active == True)
    if exclude_user_id is not None:
        q = q.filter(user_cls.id != int(exclude_user_id))
    out: List[int] = []
    for u in q.order_by(user_cls.name).all():
        if int(getattr(u, "branch_id", None) or DEFAULT_BRANCH_ID) == my_branch:
            out.append(int(u.id))
            continue
        if threshold is not None and grade_sort_order(db, grade_cls, u.grade) <= threshold:
            out.append(int(u.id))
    return out


def approver_candidate_users(
    db: Session,
    user: Any,
    *,
    user_cls: Type[Any],
    grade_cls: Type[Any],
    exclude_user_id: Optional[int] = None,
) -> List[Any]:
    ids = approver_candidate_ids(
        db, user, user_cls=user_cls, grade_cls=grade_cls, exclude_user_id=exclude_user_id
    )
    if not ids:
        return []
    by_id = {
        u.id: u
        for u in db.query(user_cls)
        .options(joinedload(user_cls.branch))
        .filter(user_cls.id.in_(ids))
        .all()
    }
    return [by_id[i] for i in ids if i in by_id]


def _approver_doc_ids_subquery(db: Session, user_id: int, approver_cls: Type[Any]) -> Set[int]:
    rows = db.query(approver_cls.doc_id).filter(approver_cls.approver_id == user_id).all()
    return {int(r[0]) for r in rows}


def visible_document_ids(
    db: Session,
    user: Any,
    *,
    document_cls: Type[Any],
    approver_cls: Type[Any],
    user_cls: Type[Any],
    view_branch_id: Optional[int] = None,
) -> Set[int]:
    """대시보드·목록: 선택(또는 소속) 지사 문서 + 결재자로 걸린 타지사 문서."""
    uid = int(user.id)
    my_branch = int(view_branch_id) if view_branch_id is not None else user_branch_id(user)
    ids: Set[int] = set()

    branch_rows = (
        db.query(document_cls.id)
        .filter(document_cls.is_deleted == False, document_cls.branch_id == my_branch)
        .all()
    )
    ids.update(int(r[0]) for r in branch_rows)

    ids.update(_approver_doc_ids_subquery(db, uid, approver_cls))

    delegators = [int(r[0]) for r in db.query(user_cls.id).filter(user_cls.delegate_id == uid).all()]
    for did in delegators:
        ids.update(_approver_doc_ids_subquery(db, did, approver_cls))

    own_any = (
        db.query(document_cls.id)
        .filter(document_cls.is_deleted == False, document_cls.creator_id == uid)
        .all()
    )
    ids.update(int(r[0]) for r in own_any)

    return ids


def filter_documents_by_visibility(
    db: Session,
    user: Any,
    doc_ids: Sequence[int],
    *,
    document_cls: Type[Any],
    approver_cls: Type[Any],
    user_cls: Type[Any],
    view_branch_id: Optional[int] = None,
) -> List[Any]:
    allowed = visible_document_ids(
        db,
        user,
        document_cls=document_cls,
        approver_cls=approver_cls,
        user_cls=user_cls,
        view_branch_id=view_branch_id,
    )
    if not doc_ids:
        return []
    want = [i for i in doc_ids if i in allowed]
    if not want:
        return []
    rows = db.query(document_cls).filter(document_cls.id.in_(want)).all()
    by_id = {d.id: d for d in rows}
    return [by_id[i] for i in want if i in by_id]


def scope_completed_query(
    db: Session,
    user: Any,
    query: Any,
    *,
    document_cls: Type[Any],
    approver_cls: Type[Any],
    user_cls: Type[Any],
    view_branch_id: Optional[int] = None,
) -> Any:
    allowed = visible_document_ids(
        db,
        user,
        document_cls=document_cls,
        approver_cls=approver_cls,
        user_cls=user_cls,
        view_branch_id=view_branch_id,
    )
    if not allowed:
        return query.filter(document_cls.id == -1)
    return query.filter(document_cls.id.in_(list(allowed)))


def document_visible_clause_for_search(
    dialect_name: str,
    document_cls: Type[Any],
    approver_cls: Type[Any],
    user_cls: Type[Any],
    user: Any,
    user_id: int,
    delegator_ids: Sequence[int],
    *,
    view_branch_id: Optional[int] = None,
) -> Any:
    """통합 검색: 선택(또는 소속) 지사 문서 + 결재 참여 문서."""
    my_branch = int(view_branch_id) if view_branch_id is not None else user_branch_id(user)
    in_branch = document_cls.branch_id == my_branch

    as_approver = exists(
        select(1).where(
            approver_cls.doc_id == document_cls.id,
            approver_cls.approver_id == user_id,
        )
    )
    parts = [in_branch, as_approver]
    if delegator_ids:
        as_delegate = exists(
            select(1).where(
                approver_cls.doc_id == document_cls.id,
                approver_cls.approver_id.in_(list(delegator_ids)),
            )
        )
        parts.append(as_delegate)
    return (document_cls.is_deleted == False) & or_(*parts)


def allocate_doc_no(db: Session, *, branch_code: str, doc_type: str, document_cls: Type[Any]) -> str:
    """예: GENERAL-WJ-2605-001"""
    code = (branch_code or "WJ").strip().upper()[:10]
    dtype = (doc_type or "GENERAL").strip().upper()[:20]
    yymm = datetime.now().strftime("%y%m")
    prefix = f"{dtype}-{code}-{yymm}-"
    pattern = re.compile(rf"^{re.escape(prefix)}(\d{{3,}})$")
    max_seq = 0
    for (doc_no,) in db.query(document_cls.doc_no).filter(document_cls.doc_no.like(f"{prefix}%")).all():
        m = pattern.match(str(doc_no or "").strip())
        if m:
            max_seq = max(max_seq, int(m.group(1)))
    return f"{prefix}{max_seq + 1:03d}"
