"""업무일지·출장복명서 작성 대상 규칙."""

from __future__ import annotations



import os

from datetime import date

from typing import Any, List, Optional, Tuple, Type



from sqlalchemy.orm import Session



try:

    from delegation import is_user_on_leave_today

except ImportError:

    from app.delegation import is_user_on_leave_today



DOC_FINAL_STATUSES = ("APPROVED", "APPROVED_FINAL")



WORK_LOG_MIN_APPROVER_GRADE = (os.getenv("WORK_LOG_MIN_APPROVER_GRADE") or "차장").strip()

WORK_LOG_MAX_APPROVER_GRADE = (os.getenv("WORK_LOG_MAX_APPROVER_GRADE") or "대표").strip()





def _csv_list(raw: str) -> List[str]:

    return [p.strip() for p in (raw or "").split(",") if p.strip()]





def work_log_exempt_grade_names() -> List[str]:

    """업무일지 작성 제외 직급 (기본: 관리자). is_admin 과 무관."""

    raw = os.getenv("WORK_LOG_EXEMPT_GRADES", "관리자").strip()

    return _csv_list(raw)





def trip_report_writer_dept_prefixes() -> List[str]:

    """출장복명서 작성 가능 부서 (기본: 관리·측정 — 관리팀/측정팀 접두사 일치)."""

    raw = (os.getenv("TRIP_REPORT_WRITER_DEPTS") or "").strip()

    if raw:

        return _csv_list(raw)

    raw2 = (os.getenv("TRIP_REPORT_APPROVAL_DEPTS") or "관리,측정").strip()

    return _csv_list(raw2)





def trip_report_writer_dept_label() -> str:

    return ", ".join(trip_report_writer_dept_prefixes())





def _dept_matches_prefixes(dept: str, prefixes: List[str]) -> bool:

    d = (dept or "").strip()

    if not d:

        return False

    for prefix in prefixes:

        if d == prefix or d.startswith(prefix):

            return True

    return False





def grade_sort_order(db: Session, grade_cls: Type[Any], grade_name: str) -> int:

    name = (grade_name or "").strip()

    if not name:

        return 99999

    g = (

        db.query(grade_cls)

        .filter(grade_cls.name == name, grade_cls.is_active == True)

        .first()

    )

    if g:

        return int(getattr(g, "sort_order", None) or getattr(g, "level", 99999))

    g2 = db.query(grade_cls).filter(grade_cls.name == name).first()

    if g2:

        return int(getattr(g2, "sort_order", None) or getattr(g2, "level", 99999))

    return 99999





def is_work_log_exempt_grade(grade_name: str) -> bool:

    """직급명이 제외 목록과 일치할 때만 (is_admin 과 별개)."""

    g = (grade_name or "").strip()

    if not g:

        return False

    return g in work_log_exempt_grade_names()





def is_work_log_approver_grade(db: Session, grade_cls: Type[Any], grade_name: str) -> bool:

    """업무일지 결재자: 차장 이상 ~ 대표 이하 (sort_order 작을수록 높은 직급)."""

    order = grade_sort_order(db, grade_cls, grade_name)

    if order >= 99999:

        return False

    top = grade_sort_order(db, grade_cls, WORK_LOG_MAX_APPROVER_GRADE)

    floor = grade_sort_order(db, grade_cls, WORK_LOG_MIN_APPROVER_GRADE)

    if top >= 99999 and floor >= 99999:

        return False

    if top >= 99999:

        return order <= floor

    if floor >= 99999:

        return order >= top

    lo, hi = min(top, floor), max(top, floor)

    return lo <= order <= hi





def is_user_on_leave_on_date(

    db: Session,

    user_id: int,

    schedule_cls: Type[Any],

    on_date: str,

) -> bool:

    d = (on_date or "").strip()[:10]

    if not d or len(d) < 10:

        return is_user_on_leave_today(db, int(user_id), schedule_cls)

    try:

        parsed = date.fromisoformat(d)

    except ValueError:

        return False

    return is_user_on_leave_today(db, int(user_id), schedule_cls, parsed)





def user_must_submit_work_log(user: Any) -> bool:

    """업무일지 작성 대상 직급 여부 (제외 직급·비활성 제외)."""

    if not bool(getattr(user, "is_active", True)):

        return False

    if is_work_log_exempt_grade(getattr(user, "grade", "") or ""):

        return False

    return True





def user_on_trip_schedule_on_date(

    db: Session,

    user_id: int,

    on_date: str,

    *,

    schedule_cls: Type[Any],

    trip_member_cls: Type[Any],

) -> bool:

    """측정팀 일정에 출장자로 등록된 날."""

    d = (on_date or "").strip()[:10]

    if not d:

        return False

    row = (

        db.query(trip_member_cls.id)

        .join(schedule_cls, trip_member_cls.schedule_id == schedule_cls.id)

        .filter(

            trip_member_cls.user_id == int(user_id),

            schedule_cls.status == "ACTIVE",

            schedule_cls.schedule_type.like("TEAM_%"),

            schedule_cls.start_date <= d,

            schedule_cls.end_date >= d,

        )

        .first()

    )

    return row is not None





def user_has_approved_weekend_work_on_date(

    db: Session,

    user_id: int,

    on_date: str,

    *,

    document_cls: Type[Any],

) -> bool:

    d = (on_date or "").strip()[:10]

    if not d:

        return False

    row = (

        db.query(document_cls.id)

        .filter(

            document_cls.creator_id == int(user_id),

            document_cls.doc_type == "WEEKEND_WORK",

            document_cls.status.in_(DOC_FINAL_STATUSES),

            document_cls.is_deleted == False,

            document_cls.overtime_date == d,

        )

        .first()

    )

    return row is not None





def user_has_work_schedule_on_date(

    db: Session,

    user_id: int,

    on_date: str,

    *,

    entry_cls: Type[Any],

) -> bool:

    d = (on_date or "").strip()[:10]

    if not d:

        return False

    row = (

        db.query(entry_cls)

        .filter(entry_cls.user_id == int(user_id), entry_cls.work_date == d)

        .first()

    )

    if not row or bool(getattr(row, "is_day_off", False)):

        return False

    total = (

        float(getattr(row, "early_hours", 0) or 0)

        + float(getattr(row, "overtime_hours", 0) or 0)

        + float(getattr(row, "weekend_hours", 0) or 0)

    )

    return total > 0





def user_is_weekend_worker_on_date(

    db: Session,

    user_id: int,

    on_date: str,

    *,

    schedule_cls: Type[Any],

    trip_member_cls: Type[Any],

    document_cls: Type[Any],

    entry_cls: Type[Any],

) -> bool:

    """주말 업무일지 작성 대상: 출장 일정·주말근무 결재·근무표 시간."""

    if user_on_trip_schedule_on_date(

        db, user_id, on_date, schedule_cls=schedule_cls, trip_member_cls=trip_member_cls

    ):

        return True

    if user_has_approved_weekend_work_on_date(

        db, user_id, on_date, document_cls=document_cls

    ):

        return True

    if user_has_work_schedule_on_date(db, user_id, on_date, entry_cls=entry_cls):

        return True

    return False





def user_must_write_work_log_on_date(

    db: Session,

    user: Any,

    on_date: str,

    *,

    schedule_cls: Type[Any],

    trip_member_cls: Type[Any],

    document_cls: Type[Any],

    entry_cls: Type[Any],

) -> Tuple[bool, str]:

    """평일: 휴가·제외 직급 제외 전원. 주말: 근무자(출장·주말근무·근무표)만."""

    if not user_must_submit_work_log(user):

        return False, "업무일지 작성 대상에서 제외된 직급입니다."

    d = (on_date or "").strip()[:10]

    if not d or len(d) < 10:

        return False, "업무일지 작성일을 입력하세요."

    try:

        parsed = date.fromisoformat(d)

    except ValueError:

        return False, "날짜 형식이 올바르지 않습니다."

    if is_user_on_leave_on_date(db, int(user.id), schedule_cls, d):

        return False, f"{d} 은(는) 휴가로 등록되어 업무일지를 작성하지 않습니다."

    if parsed.weekday() < 5:

        return True, ""

    if user_is_weekend_worker_on_date(

        db,

        int(user.id),

        d,

        schedule_cls=schedule_cls,

        trip_member_cls=trip_member_cls,

        document_cls=document_cls,

        entry_cls=entry_cls,

    ):

        return True, ""

    return False, f"{d} 은(는) 주말 — 근무 대상자만 업무일지를 작성합니다."





def user_can_submit_trip_report(user: Any) -> Tuple[bool, str]:

    """출장복명서 — 관리·측정 부서(접두사 일치)만 작성. is_admin 만으로는 불가."""

    if not bool(getattr(user, "is_active", True)):

        return False, "비활성 계정은 출장복명서를 작성할 수 없습니다."

    dept = (getattr(user, "dept", "") or "").strip()

    if _dept_matches_prefixes(dept, trip_report_writer_dept_prefixes()):

        return True, ""

    label = trip_report_writer_dept_label()

    return (

        False,

        f"출장복명서는 {label} 소속만 작성할 수 있습니다. (현재 부서: {dept or '미지정'})",

    )





def has_work_log_for_date(

    db: Session,

    user_id: int,

    work_date: str,

    *,

    document_cls: Type[Any],

    worklog_cls: Type[Any],

) -> bool:

    d = (work_date or "").strip()[:10]

    if not d:

        return False

    row = (

        db.query(document_cls.id)

        .join(worklog_cls, worklog_cls.doc_id == document_cls.id)

        .filter(

            document_cls.creator_id == int(user_id),

            document_cls.doc_type == "WORK_LOG",

            document_cls.is_deleted == False,

            worklog_cls.work_date == d,

        )

        .first()

    )

    return row is not None





def work_log_manager_users(

    db: Session,

    branch_id: int,

    work_date: str,

    *,

    user_cls: Type[Any],

    grade_cls: Type[Any],

    schedule_cls: Type[Any],

) -> List[Any]:

    """업무일지 결재선: 동일 지사 · 차장~대표."""

    d = (work_date or "").strip()[:10]

    q = db.query(user_cls).filter(

        user_cls.is_active == True,

        user_cls.branch_id == int(branch_id),

    )

    out: List[Any] = []

    for u in q.order_by(user_cls.name).all():

        if not is_work_log_approver_grade(db, grade_cls, getattr(u, "grade", "") or ""):

            continue

        if d and is_user_on_leave_on_date(db, int(u.id), schedule_cls, d):

            continue

        out.append(u)

    return out





def can_submit_work_log(

    db: Session,

    user: Any,

    work_date: str,

    *,

    schedule_cls: Type[Any],

    trip_member_cls: Type[Any],

    document_cls: Type[Any],

    worklog_cls: Type[Any],

    entry_cls: Type[Any],

) -> Tuple[bool, str]:

    """업무일지 작성 가능 여부."""

    ok, msg = user_must_write_work_log_on_date(

        db,

        user,

        work_date,

        schedule_cls=schedule_cls,

        trip_member_cls=trip_member_cls,

        document_cls=document_cls,

        entry_cls=entry_cls,

    )

    if not ok:

        return False, msg

    d = (work_date or "").strip()[:10]

    if has_work_log_for_date(

        db, int(user.id), d, document_cls=document_cls, worklog_cls=worklog_cls

    ):

        return False, f"{d} 업무일지는 이미 등록되어 있습니다."

    return True, ""





def work_log_duty_status(

    db: Session,

    user: Any,

    on_date: Optional[str] = None,

    *,

    schedule_cls: Type[Any],

    trip_member_cls: Type[Any],

    document_cls: Type[Any],

    worklog_cls: Type[Any],

    entry_cls: Type[Any],

) -> dict:

    """대시보드용: 오늘(또는 지정일) 업무일지 의무 상태."""

    d = (on_date or date.today().isoformat())[:10]

    out = {

        "date": d,

        "required": False,

        "exempt": False,

        "on_leave": False,

        "weekend_off": False,

        "submitted": False,

        "missing": False,

        "message": "",

    }

    if not user_must_submit_work_log(user):

        out["exempt"] = True

        out["message"] = "업무일지 작성 제외 직급입니다."

        return out

    if is_user_on_leave_on_date(db, int(user.id), schedule_cls, d):

        out["on_leave"] = True

        out["message"] = f"{d} 휴가 — 업무일지 제외"

        return out

    try:

        parsed = date.fromisoformat(d)

    except ValueError:

        out["message"] = "날짜 형식 오류"

        return out

    if parsed.weekday() >= 5 and not user_is_weekend_worker_on_date(

        db,

        int(user.id),

        d,

        schedule_cls=schedule_cls,

        trip_member_cls=trip_member_cls,

        document_cls=document_cls,

        entry_cls=entry_cls,

    ):

        out["weekend_off"] = True

        out["message"] = f"{d} 주말 — 근무 대상자만 업무일지 작성"

        return out

    out["required"] = True

    if has_work_log_for_date(

        db, int(user.id), d, document_cls=document_cls, worklog_cls=worklog_cls

    ):

        out["submitted"] = True

        out["message"] = f"{d} 업무일지 작성 완료"

        return out

    out["missing"] = True

    out["message"] = f"{d} 업무일지를 작성해 주세요."

    return out


