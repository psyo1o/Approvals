"""휴가(연차) 사용 집계 — 당해 1/1~12/31 기준, 지사별."""
from __future__ import annotations

import os
import re
from datetime import date
from typing import Any, Dict, List, Optional, Type

APPROVED_LEAVE_STATUSES = ("APPROVED_FINAL", "APPROVED")
PENDING_LEAVE_STATUSES = ("IN_REVIEW",)

# 근무 8.5시간 = 연차 1일, 외출 기본 30분/회
WORK_DAY_HOURS = float(os.getenv("WORK_DAY_HOURS", "8.5"))
OUTING_UNIT_MINUTES = int(os.getenv("OUTING_UNIT_MINUTES", "30"))
OUTING_KIND_NAME = (os.getenv("OUTING_LEAVE_KIND_NAME") or "외출").strip()


def work_day_minutes() -> float:
    return WORK_DAY_HOURS * 60.0


def annual_equiv_from_minutes(minutes: float) -> float:
    """외출·시간 단위 휴가 → 연차 일수 환산."""
    if minutes <= 0:
        return 0.0
    return minutes / work_day_minutes()


def parse_leave_duration_minutes(leave_hours: str) -> Optional[float]:
    """예: 30분, 0.5h, 1시간, 90, 1h30m"""
    s = (leave_hours or "").strip().lower().replace(" ", "")
    if not s:
        return None
    total = 0.0
    for m in re.finditer(r"(\d+(?:\.\d+)?)시간", s):
        total += float(m.group(1)) * 60.0
    for m in re.finditer(r"(\d+(?:\.\d+)?)h", s):
        total += float(m.group(1)) * 60.0
    for m in re.finditer(r"(\d+(?:\.\d+)?)분", s):
        total += float(m.group(1))
    for m in re.finditer(r"(\d+(?:\.\d+)?)m(?!in)", s):
        total += float(m.group(1))
    if total > 0:
        return total
    m = re.match(r"^(\d+(?:\.\d+)?)$", s)
    if not m:
        return None
    v = float(m.group(1))
    if v <= WORK_DAY_HOURS:
        return v * 60.0
    return v


def _parse_ymd(raw: str) -> Optional[date]:
    s = (raw or "").strip()[:10]
    if len(s) < 10:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def year_window(year: int) -> tuple[date, date]:
    y = int(year)
    return date(y, 1, 1), date(y, 12, 31)


def _overlap_days(start: date, end: date, win_start: date, win_end: date) -> int:
    a = max(start, win_start)
    b = min(end, win_end)
    if b < a:
        return 0
    return (b - a).days + 1


def _empty_units() -> Dict[str, float]:
    return {
        "annual": 0.0,
        "half": 0.0,
        "outing_minutes": 0.0,
        "sick": 0.0,
        "official": 0.0,
        "other": 0.0,
        "annual_equiv": 0.0,
    }


def leave_units_for_year(
    leave_kind: str,
    leave_start: str,
    leave_end: str,
    *,
    year: int,
    leave_hours: str = "",
) -> Dict[str, float]:
    """해당 연도에 겹치는 휴가 일수(연차 환산 포함)."""
    out = _empty_units()
    d0 = _parse_ymd(leave_start)
    d1 = _parse_ymd(leave_end) or d0
    if not d0:
        return out
    if d1 < d0:
        d0, d1 = d1, d0
    ws, we = year_window(year)
    if _overlap_days(d0, d1, ws, we) == 0:
        return out

    kind = (leave_kind or "").strip()
    if kind == OUTING_KIND_NAME:
        mins = parse_leave_duration_minutes(leave_hours) or float(OUTING_UNIT_MINUTES)
        out["outing_minutes"] = mins
        out["annual_equiv"] = annual_equiv_from_minutes(mins)
        return out
    if kind == "연차":
        out["annual"] = float(_overlap_days(d0, d1, ws, we))
    elif kind.startswith("반차"):
        out["half"] = 0.5
    elif kind == "병가":
        out["sick"] = float(_overlap_days(d0, d1, ws, we))
    elif kind == "공가":
        out["official"] = float(_overlap_days(d0, d1, ws, we))
    else:
        out["other"] = float(_overlap_days(d0, d1, ws, we))

    out["annual_equiv"] = out["annual"] + out["half"]
    return out


def _merge_units(acc: Dict[str, float], add: Dict[str, float]) -> None:
    for k in acc:
        acc[k] += float(add.get(k, 0) or 0)


def build_branch_leave_status(
    db: Any,
    branch_id: int,
    year: int,
    *,
    user_cls: Type[Any],
    document_cls: Type[Any],
) -> Dict[str, Any]:
    """지사별 직원 휴가 사용 현황 (승인 완료 + 결재중 건수)."""
    ws, we = year_window(year)
    year_label = f"{year}년 1월 1일 ~ 12월 31일"

    users = (
        db.query(user_cls)
        .filter(user_cls.branch_id == int(branch_id), user_cls.is_active == True)
        .order_by(user_cls.dept, user_cls.name)
        .all()
    )
    by_id: Dict[int, Dict[str, Any]] = {}
    for u in users:
        by_id[int(u.id)] = {
            "user_id": int(u.id),
            "name": getattr(u, "name", "") or "",
            "dept": getattr(u, "dept", "") or "",
            "grade": getattr(u, "grade", "") or "",
            "units": _empty_units(),
            "pending_count": 0,
            "records": [],
        }

    uid_list = list(by_id.keys())
    if not uid_list:
        return {
            "year": year,
            "year_label": year_label,
            "rows": [],
            "totals": _empty_units(),
            "pending_total": 0,
        }

    docs = (
        db.query(document_cls)
        .filter(
            document_cls.creator_id.in_(uid_list),
            document_cls.doc_type == "LEAVE",
            document_cls.is_deleted == False,
            document_cls.status.in_(APPROVED_LEAVE_STATUSES + PENDING_LEAVE_STATUSES),
        )
        .order_by(document_cls.leave_start, document_cls.id)
        .all()
    )

    totals = _empty_units()
    pending_total = 0

    for doc in docs:
        uid = int(doc.creator_id)
        if uid not in by_id:
            continue
        kind = str(getattr(doc, "leave_kind", "") or "")
        start = str(getattr(doc, "leave_start", "") or "")
        end = str(getattr(doc, "leave_end", "") or "")
        hours = str(getattr(doc, "leave_hours", "") or "")
        status = str(getattr(doc, "status", "") or "")

        if status in PENDING_LEAVE_STATUSES:
            d0 = _parse_ymd(start)
            d1 = _parse_ymd(end) or d0
            if d0 and _overlap_days(d0, d1 or d0, ws, we) > 0:
                by_id[uid]["pending_count"] += 1
                pending_total += 1
            continue

        units = leave_units_for_year(kind, start, end, year=year, leave_hours=hours)
        if units["annual_equiv"] == 0 and sum(units[k] for k in ("sick", "official", "other")) == 0:
            continue

        _merge_units(by_id[uid]["units"], units)
        _merge_units(totals, units)
        rec = {
            "doc_id": int(doc.id),
            "doc_no": str(getattr(doc, "doc_no", "") or ""),
            "leave_kind": kind,
            "leave_start": start,
            "leave_end": end,
            "leave_hours": hours,
            "status": status,
            "annual_equiv": units["annual_equiv"],
            "annual": units["annual"],
            "half": units["half"],
            "outing_minutes": units["outing_minutes"],
        }
        by_id[uid]["records"].append(rec)

    rows = []
    for row in by_id.values():
        u = row["units"]
        row["annual_equiv"] = u["annual_equiv"]
        rows.append(row)
    rows.sort(key=lambda r: (r["dept"], r["name"]))

    return {
        "year": year,
        "year_label": year_label,
        "rows": rows,
        "totals": totals,
        "pending_total": pending_total,
    }
