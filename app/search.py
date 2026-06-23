"""글로벌 통합 검색 (Phase 6.2)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, List, Optional, Sequence, Type

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

try:
    from branch_scope import document_visible_clause_for_search
except ImportError:
    from app.branch_scope import document_visible_clause_for_search

SEARCH_MIN_LEN = 2
SEARCH_LIMIT = 20

VALID_TABS = frozenset({"all", "document", "post", "attachment"})

KIND_LABELS = {
    "document": "결재문서",
    "post": "게시판",
    "attachment": "첨부파일",
}

KIND_BADGE = {
    "document": "badge-blue",
    "post": "badge-green",
    "attachment": "badge-amber",
}


@dataclass
class SearchHit:
    kind: str
    id: int
    title: str
    snippet: str
    url: str
    meta: str = ""
    sort_at: Optional[datetime] = None


def _normalize_query(q: str) -> str:
    return " ".join((q or "").split())


def _like_pattern(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _col_ilike(dialect_name: str, column: Any, pattern: str) -> Any:
    if dialect_name == "postgresql":
        return column.ilike(pattern, escape="\\")
    return func.lower(column).like(func.lower(pattern), escape="\\")


def _delegator_ids(db: Session, user_cls: Type[Any], user_id: int) -> List[int]:
    rows = db.query(user_cls.id).filter(user_cls.delegate_id == user_id, user_cls.is_active == True).all()
    return [int(r[0]) for r in rows]


def _text_match_clause(dialect_name: str, q: str, *columns: Any) -> Any:
    pattern = _like_pattern(q)
    return or_(*[_col_ilike(dialect_name, col, pattern) for col in columns])


def _make_snippet(text: Optional[str], q: str, max_len: int = 140) -> str:
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if not raw:
        return ""
    if len(raw) <= max_len:
        return raw
    lower_raw = raw.lower()
    lower_q = q.lower()
    idx = lower_raw.find(lower_q)
    if idx < 0:
        return raw[: max_len - 1] + "…"
    start = max(0, idx - 40)
    end = min(len(raw), start + max_len)
    snippet = raw[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(raw):
        snippet = snippet + "…"
    return snippet


def _search_documents(
    db: Session,
    dialect_name: str,
    user: Any,
    q: str,
    limit: int,
    document_cls: Type[Any],
    approver_cls: Type[Any],
    user_cls: Type[Any],
    status_ko: Callable[[str], str],
    doctype_ko: Callable[[str], str],
    *,
    view_branch_id: Optional[int] = None,
) -> List[SearchHit]:
    delegators = _delegator_ids(db, user_cls, int(user.id))
    vis = document_visible_clause_for_search(
        dialect_name,
        document_cls,
        approver_cls,
        user_cls,
        user,
        int(user.id),
        delegators,
        view_branch_id=view_branch_id,
    )
    match = _text_match_clause(dialect_name, q, document_cls.title, document_cls.body)
    rows = (
        db.query(document_cls)
        .filter(vis, match)
        .order_by(document_cls.updated_at.desc(), document_cls.id.desc())
        .limit(limit)
        .all()
    )
    hits: List[SearchHit] = []
    for doc in rows:
        st = status_ko(str(getattr(doc, "status", "") or ""))
        dt = doctype_ko(str(getattr(doc, "doc_type", "") or ""))
        hits.append(
            SearchHit(
                kind="document",
                id=int(doc.id),
                title=str(doc.title or "(제목 없음)"),
                snippet=_make_snippet(str(getattr(doc, "body", "") or ""), q),
                url=f"/doc/{doc.id}",
                meta=f"{dt} · {st}",
                sort_at=getattr(doc, "updated_at", None) or getattr(doc, "created_at", None),
            )
        )
    return hits


def _search_posts(
    db: Session,
    dialect_name: str,
    q: str,
    limit: int,
    post_cls: Type[Any],
    board_cls: Type[Any],
    user_cls: Type[Any],
) -> List[SearchHit]:
    match = _text_match_clause(dialect_name, q, post_cls.title, post_cls.content)
    rows = (
        db.query(post_cls, board_cls.name.label("board_name"), user_cls.name.label("author_name"))
        .join(board_cls, board_cls.id == post_cls.board_id)
        .join(user_cls, user_cls.id == post_cls.user_id)
        .filter(match)
        .order_by(post_cls.updated_at.desc(), post_cls.id.desc())
        .limit(limit)
        .all()
    )
    hits: List[SearchHit] = []
    for post, board_name, author_name in rows:
        hits.append(
            SearchHit(
                kind="post",
                id=int(post.id),
                title=str(post.title or "(제목 없음)"),
                snippet=_make_snippet(str(getattr(post, "content", "") or ""), q),
                url=f"/post/{post.id}",
                meta=f"{board_name or '게시판'} · {author_name or ''}",
                sort_at=getattr(post, "updated_at", None) or getattr(post, "created_at", None),
            )
        )
    return hits


def _search_attachments(
    db: Session,
    dialect_name: str,
    user: Any,
    q: str,
    limit: int,
    attachment_cls: Type[Any],
    document_cls: Type[Any],
    approver_cls: Type[Any],
    user_cls: Type[Any],
    *,
    view_branch_id: Optional[int] = None,
) -> List[SearchHit]:
    delegators = _delegator_ids(db, user_cls, int(user.id))
    vis = document_visible_clause_for_search(
        dialect_name,
        document_cls,
        approver_cls,
        user_cls,
        user,
        int(user.id),
        delegators,
        view_branch_id=view_branch_id,
    )
    pattern = _like_pattern(q)
    fname_match = _col_ilike(dialect_name, attachment_cls.filename, pattern)
    rows = (
        db.query(attachment_cls, document_cls)
        .join(document_cls, document_cls.id == attachment_cls.doc_id)
        .filter(vis, fname_match)
        .order_by(attachment_cls.created_at.desc(), attachment_cls.id.desc())
        .limit(limit)
        .all()
    )
    hits: List[SearchHit] = []
    for att, doc in rows:
        hits.append(
            SearchHit(
                kind="attachment",
                id=int(att.id),
                title=str(att.filename or "(파일명 없음)"),
                snippet=f"문서: {doc.title or doc.id}",
                url=f"/doc/{doc.id}",
                meta=f"문서 #{doc.id}",
                sort_at=getattr(att, "created_at", None),
            )
        )
    return hits


def run_search(
    db: Session,
    user: Any,
    q: str,
    tab: str,
    *,
    document_cls: Type[Any],
    approver_cls: Type[Any],
    user_cls: Type[Any],
    post_cls: Type[Any],
    board_cls: Type[Any],
    attachment_cls: Type[Any],
    status_ko: Callable[[str], str],
    doctype_ko: Callable[[str], str],
    view_branch_id: Optional[int] = None,
) -> dict[str, Any]:
    """통합 검색 실행. tab: all | document | post | attachment."""
    query = _normalize_query(q)
    tab_key = tab if tab in VALID_TABS else "all"

    empty: dict[str, Any] = {
        "query": query,
        "tab": tab_key,
        "too_short": False,
        "documents": [],
        "posts": [],
        "attachments": [],
        "counts": {"document": 0, "post": 0, "attachment": 0, "all": 0},
        "display_hits": [],
    }
    if len(query) < SEARCH_MIN_LEN:
        out = dict(empty)
        out["too_short"] = True
        return out

    dialect_name = db.get_bind().dialect.name

    documents: List[SearchHit] = []
    posts: List[SearchHit] = []
    attachments: List[SearchHit] = []

    if tab_key in ("all", "document"):
        documents = _search_documents(
            db, dialect_name, user, query, SEARCH_LIMIT,
            document_cls, approver_cls, user_cls, status_ko, doctype_ko,
            view_branch_id=view_branch_id,
        )
    if tab_key in ("all", "post"):
        posts = _search_posts(db, dialect_name, query, SEARCH_LIMIT, post_cls, board_cls, user_cls)
    if tab_key in ("all", "attachment"):
        attachments = _search_attachments(
            db, dialect_name, user, query, SEARCH_LIMIT,
            attachment_cls, document_cls, approver_cls, user_cls,
            view_branch_id=view_branch_id,
        )

    counts = {
        "document": len(documents),
        "post": len(posts),
        "attachment": len(attachments),
        "all": len(documents) + len(posts) + len(attachments),
    }

    if tab_key == "all":
        merged = documents + posts + attachments
        merged.sort(key=lambda h: h.sort_at or datetime.min, reverse=True)
        display = merged[:SEARCH_LIMIT * 2]
    elif tab_key == "document":
        display = documents
    elif tab_key == "post":
        display = posts
    else:
        display = attachments

    return {
        "query": query,
        "tab": tab_key,
        "too_short": False,
        "documents": documents,
        "posts": posts,
        "attachments": attachments,
        "counts": counts,
        "display_hits": display,
    }
