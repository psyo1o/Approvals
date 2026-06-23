"""근무표 — 주 52시간 검증, 조기출근·연장·주말 연동."""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Type

BASE_DAY_HOURS = float(os.getenv("BASE_DAY_HOURS", "8.5"))
WEEKLY_MAX_HOURS = float(os.getenv("WEEKLY_MAX_HOURS", "52"))
WORK_SCHEDULE_MAX_GRADE_NAME = (os.getenv("WORK_SCHEDULE_MAX_GRADE_NAME") or "이사").strip()
OFF_REASONS = ("휴무", "휴가", "공휴일")

DOC_APPROVAL_GUIDES: Dict[str, str] = {
    "TIMESHEET": "근무표(월간): 담당 → 부서장 → 감사",
    "GENERAL": "일반 기안: 담당 → 부서장 → 감사 (필요 시 추가 결재)",
    "EARLY_ARRIVAL": "조기출근: 담당 → 이사 → 대표",
    "OVERTIME": "연장근무: 담당 → 이사 → 대표",
    "WEEKEND_WORK": "주말근무: 담당 → 이사 → 대표",
    "LEAVE": "휴가·외출: 담당 → 이사 → 대표 → 고문",
    "WORK_LOG": "업무일지: 평일 전원(휴가 제외) · 주말 근무자만 · 결재 동일 지사 차장~대표",
    "TRIP_REPORT": "출장복명서: 담당 → (관리·측정팀 자동 배정, 필요 시 수정)",
    "EXPENSE": "지출결의: 담당 → 부서장 → 감사",
    "CERTIFICATE": "증명서: 담당 → 부서장 → 감사",
    "QUALITY": "품질문서: 담당 → 부서장 → 감사 (필요 시 추가)",
}


def approval_guide_for(doc_type: str) -> str:
    return DOC_APPROVAL_GUIDES.get(
        (doc_type or "").strip().upper(),
        "결재선은 담당자에 따라 직접 선택하세요.",
    )


def monday_of_week(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_dates(week_monday: date) -> List[date]:
    return [week_monday + timedelta(days=i) for i in range(7)]


def parse_ymd(raw: str) -> Optional[date]:
    s = (raw or "").strip()[:10]
    if len(s) < 10:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def default_base_hours_for_date(d: date) -> float:
    """월~금 기본 8.5h, 토·일 0 (주말근무는 weekend_hours 필드)."""
    return BASE_DAY_HOURS if d.weekday() < 5 else 0.0


def grade_sort_order(db: Any, grade_cls: Type[Any], grade_name: str) -> int:
    name = (grade_name or "").strip()
    if not name:
        return 99999
    g = db.query(grade_cls).filter(grade_cls.name == name).first()
    if g:
        return int(getattr(g, "sort_order", None) or getattr(g, "level", 99999))
    return 99999


def is_excluded_from_work_schedule(db: Any, grade_cls: Type[Any], grade_name: str) -> bool:
    """이사 및 그 위 직급 — 근무표(수당 집계) 대상에서 제외."""
    anchor = (
        db.query(grade_cls)
        .filter(grade_cls.name == WORK_SCHEDULE_MAX_GRADE_NAME, grade_cls.is_active == True)
        .first()
    )
    if not anchor:
        return False
    threshold = int(getattr(anchor, "sort_order", None) or getattr(anchor, "level", 99999))
    return grade_sort_order(db, grade_cls, grade_name) <= threshold


def _date_in_range(d: date, start: date, end: date) -> bool:
    return start <= d <= end


def leave_off_labels_for_user(
    db: Any,
    user_id: int,
    date_keys: List[str],
    *,
    schedule_cls: Type[Any],
    document_cls: Type[Any],
) -> Dict[str, str]:
    """승인 휴가·일정 LEAVE → 해당 일자 휴무(자동 표시). date -> 사유."""
    out: Dict[str, str] = {}
    for dk in date_keys:
        d = parse_ymd(dk)
        if not d:
            continue
        rows = (
            db.query(schedule_cls)
            .filter(
                schedule_cls.user_id == int(user_id),
                schedule_cls.schedule_type == "LEAVE",
                schedule_cls.status == "ACTIVE",
                schedule_cls.start_date <= dk,
                schedule_cls.end_date >= dk,
            )
            .all()
        )
        if rows:
            out[dk] = "휴가"
            continue
        docs = (
            db.query(document_cls)
            .filter(
                document_cls.creator_id == int(user_id),
                document_cls.doc_type == "LEAVE",
                document_cls.is_deleted == False,
                document_cls.status.in_(("APPROVED_FINAL", "APPROVED")),
                document_cls.leave_start <= dk,
                document_cls.leave_end >= dk,
            )
            .all()
        )
        if docs:
            out[dk] = "휴가"
    return out


def parse_hours_value(raw: Any) -> float:
    s = str(raw or "").strip().replace(",", ".")
    if not s:
        return 0.0
    try:
        return max(0.0, float(s))
    except ValueError:
        return 0.0


def parse_time_range_hours(start: str, end: str) -> float:
    """HH:MM ~ HH:MM → 시간(음수면 0)."""
    def _to_minutes(t: str) -> Optional[int]:
        t = (t or "").strip()
        m = re.match(r"^(\d{1,2}):(\d{2})$", t)
        if not m:
            return None
        return int(m.group(1)) * 60 + int(m.group(2))

    a, b = _to_minutes(start), _to_minutes(end)
    if a is None or b is None:
        return 0.0
    diff = b - a
    if diff <= 0:
        diff += 24 * 60
    return round(diff / 60.0, 2)


def day_total_hours(
    d: date,
    *,
    early: float = 0.0,
    overtime: float = 0.0,
    weekend: float = 0.0,
    is_off: bool = False,
) -> float:
    if is_off:
        return round(early + overtime + weekend, 2)
    return round(default_base_hours_for_date(d) + early + overtime + weekend, 2)


def week_total_hours(days: List[Dict[str, Any]]) -> float:
    return round(sum(float(d.get("total") or 0) for d in days), 2)


def week_payroll_sums(days: List[Dict[str, Any]]) -> Dict[str, float]:
    """수당용 주간 합계."""
    early = sum(float(d.get("early_hours") or 0) for d in days)
    ot = sum(float(d.get("overtime_hours") or 0) for d in days)
    we = sum(float(d.get("weekend_hours") or 0) for d in days)
    return {
        "early": round(early, 2),
        "overtime": round(ot, 2),
        "early_overtime": round(early + ot, 2),
        "weekend": round(we, 2),
    }


def build_week_row(
    entry: Any,
    d: date,
    *,
    auto_off_label: str = "",
) -> Dict[str, Any]:
    manual_off = bool(getattr(entry, "is_day_off", False)) if entry else False
    off_reason = (getattr(entry, "off_reason", "") or "") if entry else ""
    if manual_off:
        is_off = True
        off_label = off_reason or "휴무"
    elif auto_off_label:
        is_off = True
        off_label = auto_off_label
    else:
        is_off = False
        off_label = ""

    early = 0.0 if is_off else parse_hours_value(getattr(entry, "early_hours", 0) if entry else 0)
    ot = 0.0 if is_off else parse_hours_value(getattr(entry, "overtime_hours", 0) if entry else 0)
    we = 0.0 if is_off else parse_hours_value(getattr(entry, "weekend_hours", 0) if entry else 0)
    base = 0.0 if is_off else default_base_hours_for_date(d)
    total = day_total_hours(d, early=early, overtime=ot, weekend=we, is_off=is_off)
    return {
        "date": d.isoformat(),
        "weekday": "월화수목금토일"[d.weekday()],
        "is_weekend": d.weekday() >= 5,
        "is_off": is_off,
        "off_label": off_label,
        "base_hours": base,
        "early_hours": early,
        "overtime_hours": ot,
        "weekend_hours": we,
        "total": total,
        "note": (getattr(entry, "note", "") or "") if entry else "",
        "source_doc_id": getattr(entry, "source_doc_id", None) if entry else None,
        "entry_id": getattr(entry, "id", None) if entry else None,
    }


def upsert_schedule_entry(
    db: Any,
    *,
    entry_cls: Type[Any],
    user_id: int,
    branch_id: int,
    work_date: str,
    early_hours: Optional[float] = None,
    overtime_hours: Optional[float] = None,
    weekend_hours: Optional[float] = None,
    note: Optional[str] = None,
    source_doc_id: Optional[int] = None,
    add_early: float = 0.0,
    add_overtime: float = 0.0,
    add_weekend: float = 0.0,
    is_day_off: Optional[bool] = None,
    off_reason: Optional[str] = None,
) -> Any:
    """일자별 근무 행 생성·갱신 (결재 연동 시 시간 가산)."""
    d = (work_date or "")[:10]
    row = (
        db.query(entry_cls)
        .filter(entry_cls.user_id == int(user_id), entry_cls.work_date == d)
        .first()
    )
    if not row:
        row = entry_cls(
            user_id=int(user_id),
            branch_id=int(branch_id),
            work_date=d,
            early_hours=0.0,
            overtime_hours=0.0,
            weekend_hours=0.0,
            is_day_off=False,
            off_reason="",
            note="",
        )
        db.add(row)
        db.flush()
    if is_day_off is not None:
        row.is_day_off = bool(is_day_off)
        if row.is_day_off:
            row.early_hours = 0.0
            row.overtime_hours = 0.0
            row.weekend_hours = 0.0
            row.off_reason = (off_reason or "휴무").strip()[:30]
        else:
            row.off_reason = ""
    if off_reason is not None and not bool(getattr(row, "is_day_off", False)):
        row.off_reason = off_reason.strip()[:30]
    if early_hours is not None and not bool(getattr(row, "is_day_off", False)):
        row.early_hours = parse_hours_value(early_hours)
    elif add_early and not bool(getattr(row, "is_day_off", False)):
        row.early_hours = parse_hours_value(row.early_hours) + add_early
    if overtime_hours is not None and not bool(getattr(row, "is_day_off", False)):
        row.overtime_hours = parse_hours_value(overtime_hours)
    elif add_overtime and not bool(getattr(row, "is_day_off", False)):
        row.overtime_hours = parse_hours_value(row.overtime_hours) + add_overtime
    if weekend_hours is not None and not bool(getattr(row, "is_day_off", False)):
        row.weekend_hours = parse_hours_value(weekend_hours)
    elif add_weekend and not bool(getattr(row, "is_day_off", False)):
        row.weekend_hours = parse_hours_value(row.weekend_hours) + add_weekend
    if note is not None:
        row.note = note
    if source_doc_id is not None:
        row.source_doc_id = source_doc_id
    row.updated_at = datetime.now()
    return row


def sync_schedule_from_approved_doc(
    db: Any,
    doc: Any,
    *,
    entry_cls: Type[Any],
    user_cls: Type[Any],
) -> None:
    """연장·조기·주말 결재 완료 시 근무표 반영."""
    dtype = str(getattr(doc, "doc_type", "") or "").upper()
    if dtype not in ("OVERTIME", "EARLY_ARRIVAL", "WEEKEND_WORK"):
        return
    work_date = str(getattr(doc, "overtime_date", "") or "")[:10]
    if not work_date:
        return
    creator = db.get(user_cls, int(doc.creator_id))
    if not creator:
        return
    bid = int(getattr(creator, "branch_id", None) or 1)
    hours = parse_hours_value(getattr(doc, "work_hours", None))
    note = (getattr(doc, "body", "") or "")[:500]
    doc_id = int(doc.id)

    if dtype == "OVERTIME":
        if hours <= 0:
            hours = parse_time_range_hours(
                str(getattr(doc, "overtime_start", "") or ""),
                str(getattr(doc, "overtime_end", "") or ""),
            )
        upsert_schedule_entry(
            db,
            entry_cls=entry_cls,
            user_id=int(creator.id),
            branch_id=bid,
            work_date=work_date,
            add_overtime=hours,
            note=note or f"연장근무 문서 #{doc_id}",
            source_doc_id=doc_id,
        )
    elif dtype == "EARLY_ARRIVAL":
        if hours <= 0:
            hours = parse_hours_value(getattr(doc, "leave_hours", None)) or BASE_DAY_HOURS / 2
        upsert_schedule_entry(
            db,
            entry_cls=entry_cls,
            user_id=int(creator.id),
            branch_id=bid,
            work_date=work_date,
            add_early=hours,
            note=note or f"조기출근 문서 #{doc_id}",
            source_doc_id=doc_id,
        )
    elif dtype == "WEEKEND_WORK":
        if hours <= 0:
            hours = parse_hours_value(getattr(doc, "leave_hours", None)) or BASE_DAY_HOURS
        upsert_schedule_entry(
            db,
            entry_cls=entry_cls,
            user_id=int(creator.id),
            branch_id=bid,
            work_date=work_date,
            add_weekend=hours,
            note=note or f"주말근무 문서 #{doc_id}",
            source_doc_id=doc_id,
        )


def month_label(year_month: str) -> str:
    ym = (year_month or "").strip()
    if len(ym) >= 7 and "-" in ym:
        y, m = ym.split("-", 1)
        return f"{y}년 {int(m)}월"
    return ym


def build_timesheet_doc_body(
    db: Any,
    user: Any,
    year_month: str,
    *,
    entry_cls: Type[Any],
) -> str:
    """월간 근무표 결재용 본문 자동 생성."""
    uid = int(user.id)
    ym = year_month.strip()
    lines = [
        f"근무표 월간 결재 — {month_label(ym)}",
        f"작성자: {getattr(user, 'name', '')} ({getattr(user, 'dept', '')})",
        f"기준: 주 최대 {WEEKLY_MAX_HOURS}시간, 평일 기본 {BASE_DAY_HOURS}시간",
        "",
    ]
    entries = (
        db.query(entry_cls)
        .filter(
            entry_cls.user_id == uid,
            entry_cls.work_date.like(f"{ym}%"),
        )
        .order_by(entry_cls.work_date)
        .all()
    )
    if not entries:
        lines.append("(해당 월 근무 기록 없음 — 근무표 탭에서 입력·결재 연동 후 상신하세요.)")
        return "\n".join(lines)

    by_week: Dict[str, List[Any]] = {}
    for e in entries:
        d = parse_ymd(e.work_date)
        if not d:
            continue
        wk = monday_of_week(d).isoformat()
        by_week.setdefault(wk, []).append(e)

    for wk in sorted(by_week.keys()):
        days = []
        mon = parse_ymd(wk)
        if not mon:
            continue
        entry_by_date = {e.work_date: e for e in by_week[wk]}
        for d in week_dates(mon):
            row = build_week_row(entry_by_date.get(d.isoformat()), d)
            if row["is_off"]:
                lines.append(
                    f"  {row['date']}({row['weekday']}) 휴무[{row['off_label']}]"
                )
                continue
            days.append(row)
        total = week_total_hours(days)
        pay = week_payroll_sums(days)
        flag = " ⚠52h초과" if total > WEEKLY_MAX_HOURS else ""
        lines.append(f"■ 주간 {wk} ~ {(mon + timedelta(days=6)).isoformat()} 합계 {total}h{flag}")
        lines.append(
            f"  수당: 조기+연장 {pay['early_overtime']}h · 주말 {pay['weekend']}h"
        )
        for row in days:
            if row["total"] <= 0 and not row["note"]:
                continue
            lines.append(
                f"  {row['date']}({row['weekday']}) "
                f"기본{row['base_hours']}+조기{row['early_hours']}+연장{row['overtime_hours']}"
                f"+주말{row['weekend_hours']}={row['total']}h"
                + (f" — {row['note'][:40]}" if row["note"] else "")
            )
        lines.append("")
    return "\n".join(lines).strip()
