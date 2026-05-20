from __future__ import annotations
# PDF 다운로드 라우트 (기존 라우트 그룹 하단에 추가)
"""
approval_mvp - single-file FastAPI MVP
 로그인/세션(쿠키 서명)
 최초 로그인 비밀번호 변경 강제
 관리자: 사용자 추가/CSV 일괄 등록/비번 초기화
 문서: 임시저장(DRAFT) -> 상신(IN_REVIEW)
 결재: 순차(SEQUENTIAL) / 병렬(PARALLEL)
 작성자/관리자: DRAFT 삭제 가능
 SQLite: /data/app.db (docker-compose에서 ./data:/data 마운트)
"""

import os
import json
import csv
import io
from urllib.parse import quote
from datetime import datetime, timezone, timedelta, date
from calendar import monthrange
from typing import Optional, List, Tuple

from markupsafe import Markup

from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime, Text, ForeignKey, func, case, and_, or_
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session, joinedload, selectinload
from sqlalchemy.exc import IntegrityError

from passlib.hash import pbkdf2_sha256
from itsdangerous import URLSafeSerializer, BadSignature

import uuid
from io import BytesIO
from pypdf import PdfReader, PdfWriter
from xhtml2pdf import pisa


# ---------------------------
# 기본 설정
# ---------------------------
APP_SECRET = os.getenv("APP_SECRET", "change-me-long-random")
ADMIN_ID = os.getenv("APP_ADMIN_ID", "admin")
ADMIN_PW = os.getenv("APP_ADMIN_PW", "admin1234!")
ADMIN_DEFAULT_PW = "changeme123!"
# 기본 데이터 디렉터리를 워크스페이스의 ./data 폴더로 설정 (로컬 테스트용)
DEFAULT_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
DATA_DIR = os.getenv("APP_DATA_DIR", DEFAULT_DATA_DIR)
DB_PATH = os.path.join(DATA_DIR, "app.db")

os.makedirs(DATA_DIR, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


# ------------------------------------------------------------
# SQLite 스키마 마이그레이션(간단 버전)
# ------------------------------------------------------------
from sqlalchemy import text as _sql_text
from sqlalchemy.exc import OperationalError as SAOperationalError

def _sqlite_cols(conn, table: str):
    rows = conn.execute(_sql_text(f"PRAGMA table_info({table})")).fetchall()
    return {r[1] for r in rows}

def _ensure_column(conn, table: str, col: str, ddl: str):
    cols = _sqlite_cols(conn, table)
    if col in cols:
        return
    conn.execute(_sql_text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
    print(f"[migrate] added column {table}.{col} ({ddl})")

def _ensure_table_exists(conn, table: str) -> bool:
    """테이블이 이미 존재하는지 확인"""
    rows = conn.execute(_sql_text(
        f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
    )).fetchall()
    return len(rows) > 0

_DEFAULT_REGION_NAMES = ("원주", "제천", "단양")

def _seed_default_regions(conn) -> None:
    """regions 테이블이 비어 있으면 기본 지역명을 삽입."""
    if not _ensure_table_exists(conn, "regions"):
        return
    count = conn.execute(_sql_text("SELECT COUNT(*) FROM regions")).scalar() or 0
    if count > 0:
        return
    for name in _DEFAULT_REGION_NAMES:
        conn.execute(_sql_text("INSERT INTO regions (name) VALUES (:name)"), {"name": name})
    print(f"[migrate] seeded {len(_DEFAULT_REGION_NAMES)} default regions")

def migrate_schema():
    """기존 DB 파일을 유지하면서, 코드에 추가된 컬럼이 없으면 ADD COLUMN으로 보강."""
    try:
        with engine.begin() as conn:
            Base.metadata.create_all(bind=engine)

            # ── 기존 documents 테이블 ──
            _ensure_column(conn, "documents", "doc_type", "TEXT DEFAULT 'GENERAL'")
            _ensure_column(conn, "documents", "doc_no", "TEXT DEFAULT ''")
            _ensure_column(conn, "documents", "rev", "INTEGER DEFAULT 1")
            _ensure_column(conn, "documents", "base_doc_id", "INTEGER")
            _ensure_column(conn, "documents", "status", "TEXT DEFAULT 'DRAFT'")
            _ensure_column(conn, "documents", "is_deleted", "INTEGER DEFAULT 0")
            _ensure_column(conn, "documents", "mode", "TEXT DEFAULT 'SEQUENTIAL'")
            _ensure_column(conn, "documents", "created_at", "TEXT DEFAULT (datetime('now'))")
            _ensure_column(conn, "documents", "updated_at", "TEXT DEFAULT (datetime('now'))")
            _ensure_column(conn, "documents", "leave_start", "TEXT DEFAULT ''")
            _ensure_column(conn, "documents", "leave_end",   "TEXT DEFAULT ''")
            _ensure_column(conn, "documents", "leave_kind",  "TEXT DEFAULT ''")
            _ensure_column(conn, "documents", "leave_hours", "TEXT DEFAULT ''")
            _ensure_column(conn, "documents", "expense_total", "INTEGER DEFAULT 0")
            _ensure_column(conn, "documents", "overtime_date", "TEXT DEFAULT ''")
            _ensure_column(conn, "documents", "overtime_start", "TEXT DEFAULT ''")
            _ensure_column(conn, "documents", "overtime_end", "TEXT DEFAULT ''")
            _ensure_column(conn, "documents", "overtime_reason", "TEXT DEFAULT ''")
            _ensure_column(conn, "documents", "cert_type", "TEXT DEFAULT ''")
            _ensure_column(conn, "documents", "cert_usage", "TEXT DEFAULT ''")

            # ── 기존 users 테이블 ──
            _ensure_column(conn, "users", "must_change_pw", "INTEGER DEFAULT 0")
            _ensure_column(conn, "users", "is_admin", "INTEGER DEFAULT 0")
            _ensure_column(conn, "users", "grade_id", "INTEGER")
            _ensure_column(conn, "users", "delegate_id", "INTEGER")

            # ── 기존 grades 테이블 ──
            _ensure_column(conn, "grades", "level", "INTEGER DEFAULT 1")
            _ensure_column(conn, "grades", "is_active", "INTEGER DEFAULT 1")

            # ── 기존 attachments 테이블 (구 스키마 보강) ──
            if _ensure_table_exists(conn, "attachments"):
                _ensure_column(conn, "attachments", "uploader_id", "INTEGER")
                _ensure_column(conn, "attachments", "filesize", "INTEGER DEFAULT 0")
                _ensure_column(conn, "attachments", "created_at", "TEXT DEFAULT (datetime('now'))")
                # uploader_id 없던 기존 행 → 문서 작성자로 보정
                conn.execute(_sql_text(
                    "UPDATE attachments SET uploader_id = ("
                    "  SELECT creator_id FROM documents WHERE documents.id = attachments.doc_id"
                    ") WHERE uploader_id IS NULL"
                ))

            # ── Phase 1 신규: schedules ──
            if _ensure_table_exists(conn, "schedules"):
                _ensure_column(conn, "schedules", "color", "TEXT DEFAULT ''")
                _ensure_column(conn, "schedules", "memo", "TEXT DEFAULT ''")
                _ensure_column(conn, "schedules", "document_id", "INTEGER")

            # ── Phase 1 신규: worklogs ──
            if _ensure_table_exists(conn, "worklogs"):
                _ensure_column(conn, "worklogs", "work_date", "TEXT DEFAULT ''")

            # ── Phase 1 신규: trip_reports ──
            if _ensure_table_exists(conn, "trip_reports"):
                _ensure_column(conn, "trip_reports", "destination", "TEXT DEFAULT ''")
                _ensure_column(conn, "trip_reports", "purpose", "TEXT DEFAULT ''")
                _ensure_column(conn, "trip_reports", "registration_file_path", "TEXT")

            # ── Phase 1 신규: quality_docs ──
            if _ensure_table_exists(conn, "quality_docs"):
                _ensure_column(conn, "quality_docs", "status", "TEXT DEFAULT 'ACTIVE'")
                _ensure_column(conn, "quality_docs", "uploader_id", "INTEGER")
                _ensure_column(conn, "quality_docs", "original_filename", "TEXT DEFAULT ''")
                _ensure_column(conn, "quality_docs", "archive_path", "TEXT DEFAULT ''")

            # ── Phase 5: 지역(regions) / 수금(collections) / 출장복명서 지역 FK ──
            if _ensure_table_exists(conn, "trip_reports"):
                _ensure_column(conn, "trip_reports", "region_id", "INTEGER")

            if _ensure_table_exists(conn, "collections"):
                _ensure_column(conn, "collections", "company_name", "TEXT DEFAULT ''")
                _ensure_column(conn, "collections", "region_name", "TEXT DEFAULT ''")
                _ensure_column(conn, "collections", "amount", "INTEGER DEFAULT 0")
                _ensure_column(conn, "collections", "collection_date", "TEXT DEFAULT ''")
                _ensure_column(conn, "collections", "note", "TEXT DEFAULT ''")

            _seed_default_regions(conn)

            # 기존 결재완료 문서 → APPROVED_FINAL (회계 집계·완료함 호환)
            conn.execute(_sql_text(
                "UPDATE documents SET status = 'APPROVED_FINAL' WHERE status = 'APPROVED'"
            ))

            print("[migrate] schema migration completed successfully")
    except Exception as e:
        print(f"[migrate] migrate_schema failed: {e}")

signer = URLSafeSerializer(APP_SECRET, salt="approval_mvp_session")

def now():
    return datetime.now(timezone.utc)

# ---------------------------
# DB Models
# ---------------------------

class Grade(Base):
    __tablename__ = "grades"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, index=True, nullable=False)
    name = Column(String(120), nullable=False, default="")
    dept = Column(String(120), nullable=False, default="")
    grade = Column(String(120), nullable=False, default="")
    is_admin = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    delegate_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    password_hash = Column(String(255), nullable=False)
    must_change_pw = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False, default="")
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    mode = Column(String(20), nullable=False, default="SEQUENTIAL")
    doc_type = Column(String(20), nullable=False, default="GENERAL")
    doc_no = Column(String(30), nullable=False, default="")
    rev = Column(Integer, nullable=False, default=1)
    base_doc_id = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="DRAFT")
    is_deleted = Column(Boolean, nullable=False, default=False)
    leave_start = Column(String(10), nullable=False, default="")
    leave_end   = Column(String(10), nullable=False, default="")
    leave_kind  = Column(String(20), nullable=False, default="")
    leave_hours = Column(String(20), nullable=False, default="")
    overtime_date = Column(String(10), nullable=False, default="")
    overtime_start = Column(String(5), nullable=False, default="")
    overtime_end = Column(String(5), nullable=False, default="")
    overtime_reason = Column(String(100), nullable=False, default="")
    cert_type = Column(String(20), nullable=False, default="")
    cert_usage = Column(String(100), nullable=False, default="")
    expense_total = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now, onupdate=now)
    creator = relationship("User", foreign_keys=[creator_id])
    approvers = relationship("Approver", back_populates="doc", cascade="all, delete-orphan")
    expense_items = relationship("ExpenseItem", back_populates="doc", cascade="all, delete-orphan")
    logs = relationship("EventLog", back_populates="doc", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="doc", cascade="all, delete-orphan")

class Approver(Base):
    __tablename__ = "approvers"
    id = Column(Integer, primary_key=True)
    doc_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    approver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    order_no = Column(Integer, nullable=False)
    action = Column(String(20), nullable=False, default="WAITING")
    acted_at = Column(DateTime(timezone=True), nullable=True)
    comment = Column(Text, nullable=False, default="")
    doc = relationship("Document", back_populates="approvers")
    approver = relationship("User", foreign_keys=[approver_id])

class ExpenseItem(Base):
    __tablename__ = "expense_items"
    id = Column(Integer, primary_key=True)
    doc_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    expense_date = Column(String(10), nullable=False, default="")
    category = Column(String(50), nullable=False, default="")
    description = Column(String(200), nullable=False, default="")
    amount = Column(Integer, nullable=False, default=0)
    note = Column(String(200), nullable=False, default="")
    doc = relationship("Document", back_populates="expense_items")

class EventLog(Base):
    __tablename__ = "event_logs"
    id = Column(Integer, primary_key=True)
    doc_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event = Column(String(40), nullable=False)
    note = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    doc = relationship("Document", back_populates="logs")
    user = relationship("User")

class Board(Base):
    __tablename__ = "boards"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(200), default="")
    created_at = Column(DateTime(timezone=True), default=now)

class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True)
    board_id = Column(Integer, ForeignKey("boards.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, default="")
    views = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=now)
    updated_at = Column(DateTime(timezone=True), default=now, onupdate=now)
    board = relationship("Board")
    author = relationship("User")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now)
    sender = relationship("User", foreign_keys=[sender_id])
    receiver = relationship("User", foreign_keys=[receiver_id])
    attachments = relationship("MessageAttachment", back_populates="message", cascade="all, delete-orphan")

class MessageAttachment(Base):
    __tablename__ = "message_attachments"
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    uploader_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    filepath = Column(String(255), nullable=False)
    filesize = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=now)
    message = relationship("Message", back_populates="attachments")
    uploader = relationship("User")

class Attachment(Base):
    __tablename__ = "attachments"
    id = Column(Integer, primary_key=True)
    doc_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    uploader_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    filepath = Column(String(255), nullable=False)
    filesize = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=now)
    doc = relationship("Document", back_populates="attachments")
    uploader = relationship("User")

class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    is_all_day = Column(Boolean, default=False)
    event_type = Column(String(20), default="PERSONAL")
    location = Column(String(100), default="")
    created_at = Column(DateTime(timezone=True), default=now)
    user = relationship("User")

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=False)
    link = Column(String(200), default="")
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=now)
    user = relationship("User")


# ---------------------------
# Phase 1 신규 모델 (일정/업무일지/출장복명서/품질문서)
# ---------------------------

class Schedule(Base):
    """일정관리 — 휴가 결재 승인 시 자동 생성, 팀/전체 일정은 수동"""
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    start_date = Column(String(10), nullable=False)
    end_date = Column(String(10), nullable=False)
    schedule_type = Column(String(30), nullable=False, default="COMPANY")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    status = Column(String(10), nullable=False, default="ACTIVE")
    color = Column(String(20), nullable=False, default="")
    memo = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    user = relationship("User", foreign_keys=[user_id])
    document = relationship("Document", foreign_keys=[document_id])


class WorkLog(Base):
    """업무일지 헤더 — Document(doc_type=WORK_LOG)와 1:1 연결"""
    __tablename__ = "worklogs"
    id = Column(Integer, primary_key=True)
    doc_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    work_date = Column(String(10), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    doc = relationship("Document", foreign_keys=[doc_id], backref="worklog")
    user = relationship("User", foreign_keys=[user_id])
    lines = relationship("WorkLogLine", back_populates="worklog",
                         cascade="all, delete-orphan", order_by="WorkLogLine.order_no")


class WorkLogLine(Base):
    """업무일지 행 — 동적 Row 추가/삭제 대응"""
    __tablename__ = "worklog_lines"
    id = Column(Integer, primary_key=True)
    worklog_id = Column(Integer, ForeignKey("worklogs.id"), nullable=False)
    order_no = Column(Integer, nullable=False, default=0)
    team_name = Column(String(50), nullable=False, default="")
    company_name = Column(String(100), nullable=False, default="")
    task_content = Column(Text, nullable=False, default="")
    mileage = Column(String(20), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    worklog = relationship("WorkLog", back_populates="lines")


# ---------------------------
# Phase 5: 회계(지역 정규화 · 수금)
# ---------------------------

class Region(Base):
    """출장/회계 지역 마스터 — 데이터 파편화 방지용 정규 테이블"""
    __tablename__ = "regions"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)


class Collection(Base):
    """수금 내역 — 미수금대장·일월계표의 수금 집계 원천"""
    __tablename__ = "collections"
    id = Column(Integer, primary_key=True)
    company_name = Column(String(100), nullable=False, default="")
    region_name = Column(String(50), nullable=False, default="")  # regions.name 과 텍스트 매칭
    amount = Column(Integer, nullable=False, default=0)
    collection_date = Column(String(10), nullable=False, default="")
    note = Column(Text, nullable=False, default="")


class TripReport(Base):
    """출장복명서/세금계산서 헤더 — Document(doc_type=TRIP_REPORT)와 1:1"""
    __tablename__ = "trip_reports"
    id = Column(Integer, primary_key=True)
    doc_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    trip_date = Column(String(10), nullable=False, default="")
    destination = Column(String(200), nullable=False, default="")
    region_id = Column(Integer, ForeignKey("regions.id"), nullable=True)
    purpose = Column(Text, nullable=False, default="")
    registration_file_path = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    doc = relationship("Document", foreign_keys=[doc_id], backref="trip_report")
    user = relationship("User", foreign_keys=[user_id])
    region = relationship("Region", foreign_keys=[region_id])
    lines = relationship("TripReportLine", back_populates="trip_report",
                         cascade="all, delete-orphan", order_by="TripReportLine.order_no")


class TripReportLine(Base):
    """출장복명서 행 — 세금계산서 내역 동적 Row"""
    __tablename__ = "trip_report_lines"
    id = Column(Integer, primary_key=True)
    trip_report_id = Column(Integer, ForeignKey("trip_reports.id"), nullable=False)
    order_no = Column(Integer, nullable=False, default=0)
    volume_no = Column(String(20), nullable=False, default="")
    doc_number = Column(String(50), nullable=False, default="")
    line_date = Column(String(10), nullable=False, default="")
    company_name = Column(String(100), nullable=False, default="")
    details = Column(Text, nullable=False, default="")
    credit_amount = Column(Integer, nullable=False, default=0)
    cash_amount = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    trip_report = relationship("TripReport", back_populates="lines")


class QualityDoc(Base):
    """품질문서 이력 — NAS 볼륨의 실 파일과 매핑, 결재로 재개정"""
    __tablename__ = "quality_docs"
    id = Column(Integer, primary_key=True)
    doc_no = Column(String(50), nullable=False, default="")
    title = Column(String(200), nullable=False, default="")
    rev_no = Column(Integer, nullable=False, default=1)
    file_path = Column(String(500), nullable=False, default="")
    original_filename = Column(String(300), nullable=False, default="")
    archive_path = Column(String(500), nullable=False, default="")
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    uploader_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String(20), nullable=False, default="ACTIVE")
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now, onupdate=now)
    document = relationship("Document", foreign_keys=[document_id])
    uploader = relationship("User", foreign_keys=[uploader_id])


def query_trip_billing_lines(db: Session, *, date_from: str = "", date_to: str = "", region_id: Optional[int] = None):
    """최종 승인(APPROVED_FINAL) 출장복명서 라인만 — 회계 청구액 집계용."""
    q = (
        db.query(TripReportLine)
        .join(TripReport, TripReportLine.trip_report_id == TripReport.id)
        .join(Document, TripReport.doc_id == Document.id)
        .filter(Document.doc_type == "TRIP_REPORT")
        .filter(Document.status == "APPROVED_FINAL")
        .filter(Document.is_deleted == False)
    )
    if date_from:
        q = q.filter(TripReportLine.line_date >= date_from)
    if date_to:
        q = q.filter(TripReportLine.line_date <= date_to)
    if region_id is not None:
        q = q.filter(TripReport.region_id == region_id)
    return q


def trip_line_billing_amount(line: TripReportLine) -> int:
    """청구액 = 외상금액 + 현금금액"""
    return int(line.credit_amount or 0) + int(line.cash_amount or 0)


def _trip_billing_amount_expr():
    return TripReportLine.credit_amount + TripReportLine.cash_amount


def _parse_accounting_period(request: Request) -> Tuple[str, str, str, str]:
    """(mode, date_from, date_to, ref) — mode: day | month | quarter | year"""
    mode = (request.query_params.get("mode") or "month").strip()
    if mode not in ("day", "month", "quarter", "year"):
        mode = "month"
    today = datetime.now().strftime("%Y-%m-%d")
    y_now, m_now = int(today[:4]), int(today[5:7])
    if mode == "day":
        ref = (request.query_params.get("date") or today).strip()[:10]
        return mode, ref, ref, ref
    if mode == "year":
        try:
            y = int((request.query_params.get("year") or str(y_now)).strip()[:4])
        except (ValueError, TypeError):
            y = y_now
        ref = f"{y:04d}"
        return mode, f"{y:04d}-01-01", f"{y:04d}-12-31", ref
    if mode == "quarter":
        try:
            y = int((request.query_params.get("year") or str(y_now)).strip()[:4])
        except (ValueError, TypeError):
            y = y_now
        try:
            q = int((request.query_params.get("quarter") or str((m_now - 1) // 3 + 1)).strip())
        except (ValueError, TypeError):
            q = (m_now - 1) // 3 + 1
        q = max(1, min(4, q))
        start_m = (q - 1) * 3 + 1
        end_m = start_m + 2
        date_from = f"{y:04d}-{start_m:02d}-01"
        last_day = monthrange(y, end_m)[1]
        date_to = f"{y:04d}-{end_m:02d}-{last_day:02d}"
        ref = f"{y:04d}-Q{q}"
        return mode, date_from, date_to, ref
    ref = (request.query_params.get("month") or today[:7]).strip()[:7]
    try:
        y, mo = map(int, ref.split("-"))
        last_day = monthrange(y, mo)[1]
        date_from = f"{y:04d}-{mo:02d}-01"
        date_to = f"{y:04d}-{mo:02d}-{last_day:02d}"
    except (ValueError, TypeError):
        ref = today[:7]
        date_from = ref + "-01"
        date_to = today
    return mode, date_from, date_to, ref


def _accounting_period_label(mode: str, ref: str, date_from: str, date_to: str) -> str:
    span = f"{date_from} ~ {date_to}"
    if mode == "day":
        try:
            d = date.fromisoformat(ref[:10])
            return f"{d.year}년 {d.month}월 {d.day}일 ({span})"
        except ValueError:
            return f"{ref} ({span})"
    if mode == "quarter" and "-Q" in ref:
        y_s, q_s = ref.split("-Q", 1)
        return f"{y_s}년 {q_s}분기 ({span})"
    if mode == "year":
        try:
            y = int(ref[:4])
            return f"{y}년 ({span})"
        except ValueError:
            return f"{ref}년 ({span})"
    if mode == "month" and len(ref) >= 7:
        try:
            y, mo = ref[:7].split("-", 1)
            return f"{int(y)}년 {int(mo)}월 ({span})"
        except ValueError:
            pass
    return f"{ref} ({span})"


def _iter_days(date_from: str, date_to: str):
    try:
        cur = date.fromisoformat(date_from)
        end = date.fromisoformat(date_to)
    except ValueError:
        return
    while cur <= end:
        yield cur.isoformat()
        cur += timedelta(days=1)


def _iter_months(date_from: str, date_to: str):
    try:
        d0 = date.fromisoformat(date_from)
        d1 = date.fromisoformat(date_to)
        cur = date(d0.year, d0.month, 1)
        end = date(d1.year, d1.month, 1)
    except ValueError:
        return
    while cur <= end:
        yield f"{cur.year:04d}-{cur.month:02d}"
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)


def _sum_trip_billing(db: Session, date_from: str, date_to: str) -> int:
    expr = _trip_billing_amount_expr()
    return int(
        query_trip_billing_lines(db, date_from=date_from, date_to=date_to)
        .with_entities(func.coalesce(func.sum(expr), 0))
        .scalar()
        or 0
    )


def _sum_collections(db: Session, date_from: str = "", date_to: str = "") -> int:
    q = db.query(func.coalesce(func.sum(Collection.amount), 0))
    if date_from:
        q = q.filter(Collection.collection_date >= date_from)
    if date_to:
        q = q.filter(Collection.collection_date <= date_to)
    return int(q.scalar() or 0)


def _cumulative_receivable(db: Session, as_of: str) -> int:
    """기준일까지 누적 미수 잔액 = 전체 청구(최종승인) − 전체 수금."""
    if not as_of:
        return 0
    billing = _sum_trip_billing(db, "", as_of)
    collection = _sum_collections(db, "", as_of)
    return billing - collection


def _bucket_end_date(bucket: str, mode: str, date_to: str) -> str:
    if mode == "month" and len(bucket) >= 10:
        return bucket[:10]
    if mode in ("quarter", "year") and len(bucket) == 7:
        try:
            y, mo = map(int, bucket.split("-", 1))
            last_day = monthrange(y, mo)[1]
            end = f"{y:04d}-{mo:02d}-{last_day:02d}"
            return end if end <= date_to else date_to
        except (ValueError, TypeError):
            pass
    return date_to


def _receivable_at_end_dates(db: Session, end_dates: List[str]) -> dict[str, int]:
    if not end_dates:
        return {}
    max_end = max(end_dates)
    bill_daily = _billing_by_day(db, "2000-01-01", max_end)
    coll_daily = _collections_by_day(db, "2000-01-01", max_end)
    event_dates = sorted(set(bill_daily) | set(coll_daily))
    running_b = running_c = 0
    ei = 0
    result: dict[str, int] = {}
    for target in sorted(set(end_dates)):
        while ei < len(event_dates) and event_dates[ei] <= target:
            d = event_dates[ei]
            running_b += bill_daily.get(d, 0)
            running_c += coll_daily.get(d, 0)
            ei += 1
        result[target] = running_b - running_c
    return result


def _billing_by_day(db: Session, date_from: str, date_to: str) -> dict[str, int]:
    expr = _trip_billing_amount_expr()
    rows = (
        query_trip_billing_lines(db, date_from=date_from, date_to=date_to)
        .with_entities(
            TripReportLine.line_date.label("day"),
            func.coalesce(func.sum(expr), 0).label("amount"),
        )
        .group_by(TripReportLine.line_date)
        .all()
    )
    return {str(r.day or ""): int(r.amount) for r in rows}


def _collections_by_day(db: Session, date_from: str, date_to: str) -> dict[str, int]:
    rows = (
        db.query(
            Collection.collection_date.label("day"),
            func.coalesce(func.sum(Collection.amount), 0).label("amount"),
        )
        .filter(
            Collection.collection_date >= date_from,
            Collection.collection_date <= date_to,
        )
        .group_by(Collection.collection_date)
        .all()
    )
    return {str(r.day or ""): int(r.amount) for r in rows}


def _billing_by_month(db: Session, date_from: str, date_to: str) -> dict[str, int]:
    expr = _trip_billing_amount_expr()
    month_key = func.substr(TripReportLine.line_date, 1, 7)
    rows = (
        query_trip_billing_lines(db, date_from=date_from, date_to=date_to)
        .with_entities(
            month_key.label("month"),
            func.coalesce(func.sum(expr), 0).label("amount"),
        )
        .group_by(month_key)
        .all()
    )
    return {str(r.month or ""): int(r.amount) for r in rows}


def _collections_by_month(db: Session, date_from: str, date_to: str) -> dict[str, int]:
    month_key = func.substr(Collection.collection_date, 1, 7)
    rows = (
        db.query(
            month_key.label("month"),
            func.coalesce(func.sum(Collection.amount), 0).label("amount"),
        )
        .filter(
            Collection.collection_date >= date_from,
            Collection.collection_date <= date_to,
        )
        .group_by(month_key)
        .all()
    )
    return {str(r.month or ""): int(r.amount) for r in rows}


def _accounting_flow_rows(
    db: Session, mode: str, date_from: str, date_to: str
) -> List[dict]:
    out: List[dict] = []
    if mode == "month":
        billing_map = _billing_by_day(db, date_from, date_to)
        collection_map = _collections_by_day(db, date_from, date_to)
        buckets = list(_iter_days(date_from, date_to))
    elif mode in ("quarter", "year"):
        billing_map = _billing_by_month(db, date_from, date_to)
        collection_map = _collections_by_month(db, date_from, date_to)
        buckets = list(_iter_months(date_from, date_to))
    else:
        return out
    end_dates = [_bucket_end_date(b, mode, date_to) for b in buckets]
    receivable_map = _receivable_at_end_dates(db, end_dates)
    for bucket in buckets:
        billing = billing_map.get(bucket, 0)
        collection = collection_map.get(bucket, 0)
        end = _bucket_end_date(bucket, mode, date_to)
        out.append({
            "bucket": bucket,
            "billing": billing,
            "collection": collection,
            "net": billing - collection,
            "receivable": receivable_map.get(end, 0),
        })
    return out


def _parse_ledger_month(request: Request) -> Tuple[str, str, str]:
    """(month_ref YYYY-MM, month_start, month_end)"""
    today = datetime.now().strftime("%Y-%m-%d")
    ref = (request.query_params.get("month") or today[:7]).strip()[:7]
    try:
        y, mo = map(int, ref.split("-"))
        last_day = monthrange(y, mo)[1]
        return ref, f"{y:04d}-{mo:02d}-01", f"{y:04d}-{mo:02d}-{last_day:02d}"
    except (ValueError, TypeError):
        ref = today[:7]
        return ref, ref + "-01", today


def _build_ledger_rows(
    db: Session,
    month_start: str,
    month_end: str,
    *,
    region_id: Optional[int] = None,
    company_q: str = "",
) -> List[dict]:
    expr = _trip_billing_amount_expr()
    region_name_expr = func.coalesce(Region.name, "")
    billing_q = (
        query_trip_billing_lines(db)
        .outerjoin(Region, TripReport.region_id == Region.id)
    )
    if region_id is not None:
        billing_q = billing_q.filter(TripReport.region_id == region_id)
    if company_q:
        billing_q = billing_q.filter(TripReportLine.company_name.ilike(f"%{company_q}%"))
    billing_rows = billing_q.with_entities(
        TripReportLine.company_name,
        region_name_expr.label("region_name"),
        func.coalesce(
            func.sum(case((TripReportLine.line_date < month_start, expr), else_=0)), 0
        ).label("billing_before"),
        func.coalesce(
            func.sum(case((
                and_(TripReportLine.line_date >= month_start, TripReportLine.line_date <= month_end),
                expr,
            ), else_=0)),
            0,
        ).label("billing_current"),
    ).group_by(TripReportLine.company_name, region_name_expr).all()

    coll_q = db.query(Collection)
    if region_id is not None:
        reg = db.query(Region).filter(Region.id == region_id).first()
        if reg:
            coll_q = coll_q.filter(Collection.region_name == reg.name)
    if company_q:
        coll_q = coll_q.filter(Collection.company_name.ilike(f"%{company_q}%"))
    coll_rows = coll_q.with_entities(
        Collection.company_name,
        Collection.region_name,
        func.coalesce(
            func.sum(case((Collection.collection_date < month_start, Collection.amount), else_=0)), 0
        ).label("coll_before"),
        func.coalesce(
            func.sum(case((
                and_(Collection.collection_date >= month_start, Collection.collection_date <= month_end),
                Collection.amount,
            ), else_=0)),
            0,
        ).label("coll_current"),
    ).group_by(Collection.company_name, Collection.region_name).all()

    merged: dict[Tuple[str, str], dict] = {}

    def _key(company: str, region: str) -> Tuple[str, str]:
        return ((company or "").strip(), (region or "").strip())

    def _ensure(company: str, region: str) -> dict:
        k = _key(company, region)
        if k not in merged:
            merged[k] = {
                "company_name": company or "-",
                "region_name": region or "-",
                "opening": 0,
                "billing_current": 0,
                "collection_current": 0,
            }
        return merged[k]

    for r in billing_rows:
        row = _ensure(str(r.company_name or ""), str(r.region_name or ""))
        row["opening"] += int(r.billing_before or 0)
        row["billing_current"] += int(r.billing_current or 0)
    for r in coll_rows:
        row = _ensure(str(r.company_name or ""), str(r.region_name or ""))
        row["opening"] -= int(r.coll_before or 0)
        row["collection_current"] += int(r.coll_current or 0)

    out: List[dict] = []
    for row in merged.values():
        opening = int(row["opening"])
        billing = int(row["billing_current"])
        collection = int(row["collection_current"])
        balance = opening + billing - collection
        if balance == 0 and not (billing or collection):
            continue
        out.append({
            "company_name": row["company_name"],
            "region_name": row["region_name"],
            "opening": opening,
            "billing_current": billing,
            "collection_current": collection,
            "balance": balance,
        })
    out.sort(key=lambda x: (x["region_name"], x["company_name"]))
    return out


# ---------------------------
# FastAPI
# ---------------------------
app = FastAPI(title="approval_mvp")

# ------------------------------------------------------------
# 표시용(한글) - 템플릿에서 쓰기 편하게 함수로 제공
# ------------------------------------------------------------
DOC_FINAL_STATUSES = ("APPROVED", "APPROVED_FINAL")

def is_doc_final(status: str) -> bool:
    return (status or "") in DOC_FINAL_STATUSES

def status_ko(status: str) -> str:
    return {
        "DRAFT": "작성중", "WAITING": "대기", "IN_PROGRESS": "결재중", "IN_REVIEW": "결재중",
        "APPROVED": "결재완료", "APPROVED_FINAL": "결재완료", "REJECTED": "반려", "DELETED": "삭제",
        "SUBMITTED": "결재중", "FINAL_LOCKED": "결재완료",
    }.get(status or "", status or "-")

def mode_ko(mode: str) -> str:
    return {"SEQUENTIAL": "순차", "PARALLEL": "병렬"}.get(mode or "", mode or "-")

def doctype_ko(dt: str) -> str:
    return {
        "GENERAL": "일반 기안", "QUALITY": "품질문서", "LEAVE": "휴가신청",
        "EXPENSE": "지출결의서", "OVERTIME": "연장근무 신청", "CERTIFICATE": "증명서 발급",
        "WORK_LOG": "업무일지", "TRIP_REPORT": "출장복명서",
    }.get(dt or "", dt or "-")

SCHEDULE_TYPES = {
    "LEAVE": "휴가",
    "COMPANY": "전체일정",
    "TEAM_1": "측정팀1",
    "TEAM_2": "측정팀2",
    "TEAM_3": "측정팀3",
    "TEAM_4": "측정팀4",
    "TEAM_5": "측정팀5",
}

def schedule_type_ko(st: str) -> str:
    return SCHEDULE_TYPES.get(st or "", st or "-")

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


def _jinja_tojson(val) -> Markup:
    return Markup(json.dumps(val, ensure_ascii=False))


templates.env.filters["tojson"] = _jinja_tojson
templates.env.filters["status_ko"] = status_ko

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ---------------------------
# DB / Auth helpers
# ---------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.close()
        raise e
    finally:
        db.close()

def hash_pw(pw: str) -> str:
    return pbkdf2_sha256.hash(str(pw))

def verify_pw(pw: str, hashed: str) -> bool:
    try:
        return pbkdf2_sha256.verify(str(pw), str(hashed))
    except Exception:
        return False

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(401, "로그인이 필요합니다.")
    try:
        data = signer.loads(token, max_age=3600*24*30)
        uid = int(data.get("uid"))
        user = db.query(User).filter(User.id == uid, User.is_active == True).first()
        if not user:
            raise HTTPException(401, "사용자를 찾을 수 없습니다.")
        return user
    except (BadSignature, Exception):
        raise HTTPException(401, "세션이 유효하지 않습니다.")

def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user or not bool(user.is_admin):
        raise HTTPException(403, "관리자 권한이 필요합니다.")
    return user


def _is_truthy_admin(val) -> bool:
    if val is None:
        return False
    s = str(val).strip().lower()
    return s in ("1", "y", "yes", "true", "on", "admin", "관리자")


def _resolve_user_grade(db: Session, grade_id_raw: str, grade_text: str) -> str:
    text = (grade_text or "").strip()
    if grade_id_raw:
        try:
            gid = int(str(grade_id_raw).strip())
            g = db.query(Grade).filter(Grade.id == gid, Grade.is_active == True).first()
            if g:
                return g.name
        except (TypeError, ValueError):
            pass
    return text


def _lookup_grade_name(db: Session, grade_cell: str) -> str:
    """CSV grade: 직급명 또는 숫자 id."""
    cell = (grade_cell or "").strip()
    if not cell:
        return ""
    if cell.isdigit():
        g = db.query(Grade).filter(Grade.id == int(cell), Grade.is_active == True).first()
        return g.name if g else ""
    g = db.query(Grade).filter(Grade.name == cell, Grade.is_active == True).first()
    return g.name if g else cell


def _count_active_admins(db: Session, exclude_user_id: Optional[int] = None) -> int:
    q = db.query(User).filter(User.is_admin == True, User.is_active == True)
    if exclude_user_id is not None:
        q = q.filter(User.id != exclude_user_id)
    return q.count()


def _admin_redirect_users(message: str = "") -> RedirectResponse:
    url = "/admin/users"
    if message:
        url += "?flash=" + quote(message, safe="")
    return RedirectResponse(url, status_code=303)


def _admin_redirect_grades(message: str = "") -> RedirectResponse:
    url = "/admin/grades"
    if message:
        url += "?flash=" + quote(message, safe="")
    return RedirectResponse(url, status_code=303)

# ------------------------------------------------------------
# 권한 유틸
# ------------------------------------------------------------
def can_view_doc(user: User, doc: Document, db: Session) -> bool:
    if user and bool(getattr(user, 'is_admin', False)):
        return True
    if int(getattr(doc, 'creator_id', -1)) == int(getattr(user, 'id', -2)):
        return True
    if db.query(Approver).filter(Approver.doc_id == doc.id, Approver.approver_id == user.id).first():
        return True
    delegators = [d.id for d in db.query(User).filter(User.delegate_id == user.id).all()]
    if delegators and db.query(Approver).filter(Approver.doc_id == doc.id, Approver.approver_id.in_(delegators)).first():
        return True
    return False

def can_edit_doc(user: User, doc: Document) -> bool:
    if user and bool(getattr(user, 'is_admin', False)):
        return True
    return (int(getattr(doc, 'creator_id', -1)) == int(getattr(user, 'id', -2))) and (str(getattr(doc, 'status', '')) == "DRAFT")

def can_approve_doc(user: User, doc: Document, db: Session) -> bool:
    if str(doc.status) != "IN_REVIEW":
        return False
    if user and bool(getattr(user, 'is_admin', False)):
        return (
            db.query(Approver)
            .filter(Approver.doc_id == doc.id, Approver.action == "PENDING")
            .first()
            is not None
        )
    allowed_ids = [user.id] + [d.id for d in db.query(User).filter(User.delegate_id == user.id).all()]
    ap = db.query(Approver).filter(Approver.doc_id == doc.id, Approver.approver_id.in_(allowed_ids)).first()
    if not ap:
        return False
    if str(doc.mode) == "SEQUENTIAL":
        pending = current_pending_approver(db, doc)
        return pending is not None and pending.approver_id in allowed_ids
    return (
        db.query(Approver)
        .filter(Approver.doc_id == doc.id, Approver.approver_id.in_(allowed_ids), Approver.action == "PENDING")
        .first()
        is not None
    )


def current_pending_approver(db: Session, doc: Document) -> Optional[Approver]:
    if str(doc.mode) != "SEQUENTIAL":
        return None
    return db.query(Approver).filter(Approver.doc_id == doc.id, Approver.action == "PENDING").order_by(Approver.order_no.asc()).first()

def update_doc_status_after_action(db: Session, doc: Document):
    approvers = db.query(Approver).filter(Approver.doc_id == doc.id).all()
    if any(a.action == "REJECTED" for a in approvers):
        setattr(doc, 'status', "REJECTED")
        _on_doc_rejected(db, doc)
    elif approvers and all(a.action == "APPROVED" for a in approvers):
        setattr(doc, 'status', "APPROVED_FINAL")
        _on_doc_approved(db, doc)
    else:
        setattr(doc, 'status', "IN_REVIEW")
    db.commit()


def _on_doc_approved(db: Session, doc: Document):
    """결재 최종 승인 시 후처리 — 휴가→일정, 품질문서→NAS 반영 등"""
    if str(getattr(doc, 'doc_type', '')) == "QUALITY":
        _quality_doc_finalize(db, doc)
    if str(getattr(doc, 'doc_type', '')) == "LEAVE":
        creator = db.get(User, doc.creator_id)
        title = f"{creator.name if creator else ''} {doc.leave_kind}".strip()
        start = str(doc.leave_start or "")
        end = str(doc.leave_end or "")
        if not db.query(Schedule).filter_by(document_id=doc.id).first():
            db.add(Schedule(
                title=title,
                start_date=start,
                end_date=end,
                schedule_type="LEAVE",
                user_id=doc.creator_id,
                document_id=doc.id,
                status="ACTIVE",
                color="#ef4444",
                memo=f"휴가 결재 자동 생성 (문서 #{doc.id})",
            ))
        # 기존 CalendarEvent 호환 유지
        try:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end) + timedelta(days=1)
        except Exception:
            start_dt = end_dt = now()
        if not db.query(CalendarEvent).filter_by(user_id=doc.creator_id, title=title, start_time=start_dt).first():
            db.add(CalendarEvent(
                user_id=doc.creator_id, title=title,
                description=f"휴가 결재 완료 (문서 #{doc.id})",
                start_time=start_dt, end_time=end_dt,
                is_all_day=True, event_type="PERSONAL",
            ))


def _on_doc_rejected(db: Session, doc: Document):
    """결재 반려 시 후처리 — 연결된 일정 취소"""
    if str(getattr(doc, 'doc_type', '')) == "LEAVE":
        sch = db.query(Schedule).filter_by(document_id=doc.id).first()
        if sch:
            sch.status = "CANCELLED"
    if str(getattr(doc, 'doc_type', '')) == "QUALITY":
        qd = db.query(QualityDoc).filter_by(document_id=doc.id).first()
        if qd:
            qd.status = "REJECTED"


import shutil as _shutil

def _quality_doc_finalize(db: Session, doc: Document):
    """품질문서 결재 승인 후 — QualityDoc ACTIVE + 아카이빙 파일 보관"""
    qd = db.query(QualityDoc).filter_by(document_id=doc.id).first()
    if not qd:
        return
    qd.status = "ACTIVE"

    db.query(QualityDoc).filter(
        QualityDoc.doc_no == qd.doc_no,
        QualityDoc.id != qd.id,
        QualityDoc.status == "ACTIVE",
    ).update({"status": "SUPERSEDED"})

    att = db.query(Attachment).filter(Attachment.doc_id == doc.id).order_by(Attachment.id.desc()).first()
    if att and os.path.isfile(att.filepath):
        qd.original_filename = att.filename

        safe_doc_no = (qd.doc_no or "unknown").replace("/", "_").replace("\\", "_")
        archive_dir = os.path.join(DATA_DIR, "quality_archive", safe_doc_no)
        os.makedirs(archive_dir, exist_ok=True)

        ext = os.path.splitext(att.filename)[1]
        date_str = datetime.now().strftime("%Y%m%d")
        archive_fname = f"{safe_doc_no}_Rev{qd.rev_no}_{date_str}{ext}"
        archive_dest = os.path.join(archive_dir, archive_fname)

        pdf_dest = ""
        if ext.lower() != ".pdf":
            pdf_src_name = os.path.splitext(att.filename)[0] + ".pdf"
            pdf_att = db.query(Attachment).filter(
                Attachment.doc_id == doc.id,
                Attachment.filename.ilike(f"%{pdf_src_name}%"),
            ).first()
            if pdf_att and os.path.isfile(pdf_att.filepath):
                pdf_archive = f"{safe_doc_no}_Rev{qd.rev_no}_{date_str}.pdf"
                pdf_dest = os.path.join(archive_dir, pdf_archive)
                try:
                    _shutil.copy2(pdf_att.filepath, pdf_dest)
                except Exception:
                    pdf_dest = ""

        try:
            _shutil.copy2(att.filepath, archive_dest)
            qd.archive_path = archive_dest
            qd.file_path = pdf_dest or archive_dest
            print(f"[quality] archived → {archive_dest}")
        except Exception as e:
            print(f"[quality] archive failed: {e}")


def _resolve_grade_name(db: Session, user: Optional[User]) -> str:
    if not user:
        return "-"
    raw = (user.grade or "").strip()
    if not raw:
        return "-"
    gr = db.query(Grade).filter(Grade.name == raw, Grade.is_active == True).first()
    return gr.name if gr else raw


def _fmt_acted_at_pdf(dt: Optional[datetime]) -> str:
    """결재란 PDF용 시각 (예: 05/14 14:32)."""
    if not dt:
        return ""
    try:
        return dt.astimezone().strftime("%m/%d %H:%M")
    except Exception:
        return str(dt)[:16]


def _fetch_approved_approvers_for_pdf(db: Session, doc_id: int) -> List[dict]:
    """order_no 오름차순 · APPROVED 결재자만 (최종 승인 완료 건)."""
    rows = (
        db.query(Approver)
        .options(joinedload(Approver.approver))
        .filter(Approver.doc_id == doc_id, Approver.action == "APPROVED")
        .order_by(Approver.order_no.asc())
        .all()
    )
    out: List[dict] = []
    for ap in rows:
        u = ap.approver
        out.append({
            "order_no": ap.order_no,
            "grade": _resolve_grade_name(db, u),
            "name": (u.name if u else "-"),
            "acted_at": _fmt_acted_at_pdf(ap.acted_at) or "-",
        })
    return out


def _nanum_font_path() -> str:
    """컨테이너 fonts-nanum 경로 (xhtml2pdf 한글 임베딩용)."""
    candidates = (
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicRegular.ttf",
        "/usr/share/fonts/opentype/nanum/NanumGothic.otf",
    )
    for path in candidates:
        if os.path.isfile(path):
            return path
    return ""


def _pdf_link_callback(uri: str, rel: str) -> str:
    if uri in ("pdf-korean.ttf", "NanumGothic.ttf"):
        return _nanum_font_path() or uri
    return uri


def _render_pdf_html(template_name: str, context: dict) -> bytes:
    font_path = _nanum_font_path()
    if not font_path:
        print("[pdf] WARNING: Nanum Gothic not found — Korean may render as boxes")
    html = templates.env.get_template(template_name).render(context)
    buf = BytesIO()
    status = pisa.CreatePDF(
        io.BytesIO(html.encode("utf-8")),
        dest=buf,
        encoding="utf-8",
        link_callback=_pdf_link_callback,
    )
    if status.err:
        raise RuntimeError(f"PDF HTML 변환 실패: {template_name}")
    return buf.getvalue()


def _approval_overlay_pdf_bytes(db: Session, doc_id: int, page_w: float, page_h: float) -> bytes:
    return _render_pdf_html(
        "pdf/approval_overlay.html",
        {
            "approvers": _fetch_approved_approvers_for_pdf(db, doc_id),
            "page_width_pt": round(page_w, 2),
            "page_height_pt": round(page_h, 2),
        },
    )


def _generate_final_pdf_text(db: Session, doc: Document, final_path: str) -> None:
    data = _render_pdf_html(
        "pdf/final_document.html",
        {
            "doc": doc,
            "approvers": _fetch_approved_approvers_for_pdf(db, doc.id),
        },
    )
    with open(final_path, "wb") as out:
        out.write(data)


def _generate_final_pdf_from_attachment(db: Session, doc: Document, src_path: str, final_path: str) -> None:
    reader = PdfReader(src_path)
    if not reader.pages:
        _generate_final_pdf_text(db, doc, final_path)
        return
    w = float(reader.pages[0].mediabox.width)
    h = float(reader.pages[0].mediabox.height)
    stamp_reader = PdfReader(BytesIO(_approval_overlay_pdf_bytes(db, doc.id, w, h)))
    stamp_page = stamp_reader.pages[0]
    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        if i == 0:
            page.merge_page(stamp_page)
        writer.add_page(page)
    with open(final_path, "wb") as out:
        writer.write(out)


def _generate_final_pdf(db: Session, doc: Document) -> Optional[str]:
    try:
        final_dir = os.path.join(DATA_DIR, "final")
        os.makedirs(final_dir, exist_ok=True)
        final_path = os.path.join(final_dir, f"final_{doc.id}.pdf")
        att = _first_attachment(db, doc.id)
        if att and att.filepath.lower().endswith(".pdf") and os.path.isfile(att.filepath):
            _generate_final_pdf_from_attachment(db, doc, att.filepath, final_path)
        else:
            _generate_final_pdf_text(db, doc, final_path)
        return final_path
    except Exception as e:
        print(f"[final_pdf] doc={doc.id} failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def _first_attachment(db: Session, doc_id: int) -> Optional[Attachment]:
    return db.query(Attachment).filter(Attachment.doc_id == doc_id).order_by(Attachment.id.asc()).first()


DEMO_COMPLETED_TITLE = "[예시] 결재란 PDF 확인용 테스트문서"
DEMO_COMPLETED_BODY = """[결재란 PDF 예시 문서]

이 문서는 전자결재 최종 승인 후 생성되는 PDF 우측 상단에
결재선(직급 · 성명 · 결재일시)이 가로로 표시되는지 확인하기 위한 샘플입니다.

■ 요청 내용
· 2026년 1분기 현장 점검 결과 보고
· 관련 비용 및 일정은 별첨 참조

■ 확인 방법
1. [완료문서] 목록에서 이 문서 선택
2. [PDF 다운로드] 클릭 → 우측 상단 결재란 4칸(사원→과장→부장→대표, 직급 낮은 순 결재) 확인

※ 실제 업무 문서가 아닌 시스템 점검용 예시입니다.
"""

# order_no 1→4: 직급 낮은 사람이 먼저 결재, 높은 사람이 나중에 결재
_DEMO_APPROVER_ACCOUNTS = (
    ("demo_ap4", "최사원", "사원"),
    ("demo_ap1", "김과장", "과장"),
    ("demo_ap2", "이부장", "부장"),
    ("demo_ap3", "박대표", "대표"),
)


def _ensure_grade_row(db: Session, name: str) -> None:
    if not db.query(Grade).filter(Grade.name == name).first():
        db.add(Grade(name=name, is_active=True))


def _ensure_demo_approver_user(db: Session, username: str, name: str, grade: str) -> User:
    _ensure_grade_row(db, grade)
    u = db.query(User).filter(User.username == username).first()
    if not u:
        u = User(
            username=username,
            name=name,
            grade=grade,
            is_active=True,
            password_hash=hash_pw(ADMIN_DEFAULT_PW),
            must_change_pw=False,
        )
        db.add(u)
        db.flush()
    else:
        u.name = name
        u.grade = grade
        u.is_active = True
    return u


def seed_demo_completed_pdf_sample(db: Session) -> Optional[int]:
    """완료함 '테스트' 문서를 결재란 PDF 예시용으로 갱신 (없으면 생성)."""
    admin = db.query(User).filter(User.username == ADMIN_ID).first()
    if not admin:
        return None

    doc = (
        db.query(Document)
        .filter(Document.is_deleted == False)
        .filter(
            or_(
                Document.title.ilike("%테스트%"),
                Document.title.ilike("%test%"),
                Document.title == DEMO_COMPLETED_TITLE,
                Document.doc_no == "DEMO-001",
            )
        )
        .order_by(Document.id.desc())
        .first()
    )
    if not doc:
        doc = Document(
            title=DEMO_COMPLETED_TITLE,
            body="",
            creator_id=admin.id,
            status="APPROVED_FINAL",
            mode="SEQUENTIAL",
            doc_type="GENERAL",
            doc_no="DEMO-001",
        )
        db.add(doc)
        db.flush()

    doc.title = DEMO_COMPLETED_TITLE
    doc.body = DEMO_COMPLETED_BODY
    doc.status = "APPROVED_FINAL"
    doc.mode = "SEQUENTIAL"
    doc.doc_type = "GENERAL"
    if not (doc.doc_no or "").strip():
        doc.doc_no = f"DEMO-{doc.id:04d}"
    doc.updated_at = now()

    demo_users: List[User] = []
    for username, name, grade in _DEMO_APPROVER_ACCOUNTS:
        demo_users.append(_ensure_demo_approver_user(db, username, name, grade))

    db.query(Approver).filter(Approver.doc_id == doc.id).delete(synchronize_session=False)

    base = now() - timedelta(days=5)
    acted_offsets = (
        timedelta(hours=9, minutes=30),
        timedelta(hours=11, minutes=15),
        timedelta(days=1, hours=14, minutes=32),
        timedelta(days=1, hours=16, minutes=5),
    )
    for i, u in enumerate(demo_users):
        db.add(
            Approver(
                doc_id=doc.id,
                approver_id=u.id,
                order_no=i + 1,
                action="APPROVED",
                acted_at=base + acted_offsets[i],
                comment="",
            )
        )

    db.commit()
    db.refresh(doc)
    _generate_final_pdf(db, doc)
    print(f"[seed] demo completed PDF sample → doc_id={doc.id} (결재자 {len(demo_users)}명)")
    return doc.id


async def _save_message_attachments(db: Session, message_id: int, uploader_id: int, form) -> int:
    upload_files = form.getlist("files") if hasattr(form, "getlist") else []
    if not upload_files:
        return 0
    upload_dir = os.path.join(DATA_DIR, "uploads", "messages", str(message_id))
    os.makedirs(upload_dir, exist_ok=True)
    saved = 0
    for file in upload_files:
        if not isinstance(file, UploadFile) or not file.filename:
            continue
        fname = f"{uuid.uuid4().hex}_{file.filename}"
        fpath = os.path.join(upload_dir, fname)
        content = await file.read()
        with open(fpath, "wb") as out:
            out.write(content)
        db.add(MessageAttachment(
            message_id=message_id,
            uploader_id=uploader_id,
            filename=file.filename,
            filepath=fpath,
            filesize=len(content),
        ))
        saved += 1
    return saved


def _can_view_message(user: User, msg: Message) -> bool:
    return msg.sender_id == user.id or msg.receiver_id == user.id


def _guess_media_type(path: str) -> str:
    lower = path.lower()
    if lower.endswith('.pdf'):
        return 'application/pdf'
    if lower.endswith(('.png',)):
        return 'image/png'
    if lower.endswith(('.jpg', '.jpeg')):
        return 'image/jpeg'
    if lower.endswith('.gif'):
        return 'image/gif'
    if lower.endswith('.webp'):
        return 'image/webp'
    return 'application/octet-stream'

def visible_docs(db: Session, user: User) -> list:
    if bool(user.is_admin):
        return db.query(Document).filter(Document.is_deleted == False).all()
    q_own = db.query(Document).filter(Document.is_deleted == False, Document.creator_id == user.id).all()
    appr_ids = list({a.doc_id for a in db.query(Approver).filter(Approver.approver_id == user.id).all()})
    q_appr = db.query(Document).filter(Document.is_deleted == False, Document.id.in_(appr_ids)).all() if appr_ids else []
    merged = {d.id: d for d in q_own + q_appr}
    return list(merged.values())

# --- 로그인/비밀번호 변경 라우트 수정 ---
@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if not user or not verify_pw(password, str(user.password_hash)):
        return templates.TemplateResponse("login.html", {"request": request, "error": "아이디 또는 비밀번호가 틀립니다."}, status_code=400)
    redirect_url = "/change-password" if bool(user.must_change_pw) else "/dashboard"
    resp = RedirectResponse(redirect_url, status_code=303)
    resp.set_cookie("session", signer.dumps({"uid": user.id}), httponly=True, samesite="lax", max_age=3600*24*30)
    return resp


@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/")
def root_redirect():
    return RedirectResponse(url="/login")


@app.on_event("startup")
def app_startup():
    # Ensure DB schema and default admin user exist
    try:
        migrate_schema()
    except Exception as e:
        print(f"[startup] migrate_schema error: {e}")
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == ADMIN_ID).first()
        if not admin:
            admin = User(username=ADMIN_ID, name="관리자", is_admin=True, is_active=True, password_hash=hash_pw(ADMIN_PW), must_change_pw=False)
            db.add(admin)
            db.commit()
            print("[startup] created default admin user")
        if os.getenv("SEED_DEMO_PDF", "1").strip().lower() not in ("0", "false", "no"):
            try:
                seed_demo_completed_pdf_sample(db)
            except Exception as e:
                print(f"[startup] seed_demo_completed_pdf_sample error: {e}")
    except Exception as e:
        print(f"[startup] admin creation error: {e}")
    finally:
        db.close()


# --- 기본 라우트들 (간단한 동작 구현) ---
@app.get("/logout")
def logout():
    resp = RedirectResponse(url="/login")
    resp.delete_cookie("session")
    return resp


@app.get("/api/regions")
def api_regions_list(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Region).order_by(Region.name.asc()).all()
    return {"regions": [{"id": r.id, "name": r.name} for r in rows]}


@app.post("/api/regions")
async def api_regions_create(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    name = ""
    try:
        body = await request.json()
        if isinstance(body, dict):
            name = str(body.get("name") or "").strip()
    except Exception:
        pass
    if not name:
        form = await request.form()
        name = str(form.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "지역명을 입력하세요.")
    if len(name) > 50:
        raise HTTPException(400, "지역명은 50자 이하여야 합니다.")
    existing = db.query(Region).filter(Region.name == name).first()
    if existing:
        return {"id": existing.id, "name": existing.name}
    reg = Region(name=name)
    db.add(reg)
    try:
        db.commit()
        db.refresh(reg)
    except IntegrityError:
        db.rollback()
        existing = db.query(Region).filter(Region.name == name).first()
        if existing:
            return {"id": existing.id, "name": existing.name}
        raise HTTPException(409, "이미 등록된 지역입니다.")
    return {"id": reg.id, "name": reg.name}


@app.get("/doc/new", response_class=HTMLResponse)
def doc_new_get(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        regions = db.query(Region).order_by(Region.name.asc()).all()
    except Exception as e:
        print(f"[doc_new] regions query failed: {e}")
        regions = []
    regions_json = json.dumps(
        [{"id": r.id, "name": r.name} for r in regions], ensure_ascii=False
    )
    return templates.TemplateResponse(
        "doc_new.html",
        {"request": request, "user": user, "regions": regions, "regions_json": regions_json},
    )


@app.post("/doc/new")
async def doc_new_post(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    form = await request.form()
    doc_type = str(form.get("doc_type") or "GENERAL")
    body = str(form.get("body") or "")
    title = str(form.get("title") or "").strip()
    doc_no = str(form.get("doc_no") or "").strip()
    leave_kind = str(form.get("leave_kind") or "")
    leave_start = str(form.get("leave_start") or "")
    leave_end = str(form.get("leave_end") or "")
    leave_hours = str(form.get("leave_hours") or "")
    overtime_date = str(form.get("overtime_date") or "")
    overtime_start = str(form.get("overtime_start") or "")
    overtime_end = str(form.get("overtime_end") or "")
    overtime_reason = str(form.get("overtime_reason") or "")
    cert_type = str(form.get("cert_type") or "")
    cert_usage = str(form.get("cert_usage") or "")
    try:
        expense_total = int(form.get("expense_total") or 0)
    except (TypeError, ValueError):
        expense_total = 0

    work_date = str(form.get("work_date") or "")
    trip_date = str(form.get("trip_date") or "")
    destination = str(form.get("destination") or "")
    purpose = str(form.get("purpose") or "")
    trip_region_id: Optional[int] = None
    raw_region_id = form.get("region_id")
    if raw_region_id not in (None, ""):
        try:
            trip_region_id = int(raw_region_id)
        except (TypeError, ValueError):
            trip_region_id = None

    if doc_type == "LEAVE" and not title:
        title = f"[휴가] {leave_kind} {leave_start}~{leave_end}".strip() or "[휴가] 신청"
    elif doc_type == "EXPENSE" and not title:
        title = f"[지출결의] 합계 {expense_total}원" if expense_total else "[지출결의]"
    elif doc_type == "OVERTIME" and not title:
        title = f"[연장근무] {overtime_date} {overtime_start}-{overtime_end}".strip() or "[연장근무]"
    elif doc_type == "CERTIFICATE" and not title:
        title = f"[증명서] {cert_type}".strip() or "[증명서]"
    elif doc_type == "QUALITY" and not title:
        title = doc_no or "[품질문서]"
    elif doc_type == "WORK_LOG" and not title:
        title = f"[업무일지] {work_date}".strip() or "[업무일지]"
    elif doc_type == "TRIP_REPORT" and not title:
        region_label = ""
        if trip_region_id:
            reg = db.query(Region).filter(Region.id == trip_region_id).first()
            if reg:
                region_label = reg.name
        title = f"[출장복명서] {region_label} {destination} {trip_date}".strip() or "[출장복명서]"

    d = Document(
        title=title or "(제목 없음)",
        body=body,
        creator_id=user.id,
        doc_type=doc_type,
        doc_no=doc_no,
        status="DRAFT",
        leave_kind=leave_kind,
        leave_start=leave_start,
        leave_end=leave_end,
        leave_hours=leave_hours,
        overtime_date=overtime_date,
        overtime_start=overtime_start,
        overtime_end=overtime_end,
        overtime_reason=overtime_reason,
        cert_type=cert_type,
        cert_usage=cert_usage,
        expense_total=expense_total,
    )
    db.add(d)
    db.commit()
    db.refresh(d)

    exp_dates = form.getlist("exp_date") if hasattr(form, "getlist") else []
    if doc_type == "EXPENSE" and exp_dates:
        for i in range(len(exp_dates)):
            ed = str(exp_dates[i] or "")
            cats = form.getlist("exp_cat") if hasattr(form, "getlist") else []
            descs = form.getlist("exp_desc") if hasattr(form, "getlist") else []
            amts = form.getlist("exp_amt") if hasattr(form, "getlist") else []
            notes = form.getlist("exp_note") if hasattr(form, "getlist") else []
            cat = str(cats[i]) if i < len(cats) else ""
            desc = str(descs[i]) if i < len(descs) else ""
            note = str(notes[i]) if i < len(notes) else ""
            amt_raw = str(amts[i] or "0").replace(",", "").strip()
            try:
                amt = int(amt_raw) if amt_raw else 0
            except ValueError:
                amt = 0
            if ed or desc or amt:
                db.add(ExpenseItem(doc_id=d.id, expense_date=ed, category=cat, description=desc, amount=amt, note=note))
        db.commit()

    upload_files = form.getlist("files") if hasattr(form, "getlist") else []
    if upload_files:
        upload_dir = os.path.join(DATA_DIR, "uploads", str(d.id))
        os.makedirs(upload_dir, exist_ok=True)
        for file in upload_files:
            if not isinstance(file, UploadFile) or not file.filename:
                continue
            fname = f"{uuid.uuid4().hex}_{file.filename}"
            fpath = os.path.join(upload_dir, fname)
            with open(fpath, "wb") as out:
                content = await file.read()
                out.write(content)
            db.add(Attachment(doc_id=d.id, uploader_id=user.id, filename=file.filename, filepath=fpath, filesize=len(content)))
        db.commit()

    # ── 업무일지 (WORK_LOG) 행 저장 ──
    if doc_type == "WORK_LOG":
        wl = WorkLog(doc_id=d.id, user_id=user.id, work_date=work_date)
        db.add(wl)
        db.flush()
        wl_teams = form.getlist("wl_team") if hasattr(form, "getlist") else []
        wl_companies = form.getlist("wl_company") if hasattr(form, "getlist") else []
        wl_contents = form.getlist("wl_content") if hasattr(form, "getlist") else []
        wl_mileages = form.getlist("wl_mileage") if hasattr(form, "getlist") else []
        for i in range(len(wl_contents)):
            content_val = str(wl_contents[i]) if i < len(wl_contents) else ""
            if not content_val.strip():
                continue
            db.add(WorkLogLine(
                worklog_id=wl.id,
                order_no=i + 1,
                team_name=str(wl_teams[i]) if i < len(wl_teams) else "",
                company_name=str(wl_companies[i]) if i < len(wl_companies) else "",
                task_content=content_val,
                mileage=str(wl_mileages[i]) if i < len(wl_mileages) else "",
            ))
        db.commit()

    # ── 출장복명서 (TRIP_REPORT) 행 + 사업자등록증 파일 저장 ──
    if doc_type == "TRIP_REPORT":
        if trip_region_id and not db.query(Region).filter(Region.id == trip_region_id).first():
            trip_region_id = None
        reg_file = form.get("registration_file")
        reg_path = None
        if isinstance(reg_file, UploadFile) and reg_file.filename:
            reg_dir = os.path.join(DATA_DIR, "uploads", str(d.id))
            os.makedirs(reg_dir, exist_ok=True)
            reg_fname = f"reg_{uuid.uuid4().hex}_{reg_file.filename}"
            reg_path = os.path.join(reg_dir, reg_fname)
            with open(reg_path, "wb") as out:
                reg_content = await reg_file.read()
                out.write(reg_content)

        tr = TripReport(
            doc_id=d.id, user_id=user.id,
            trip_date=trip_date, destination=destination,
            region_id=trip_region_id,
            purpose=purpose, registration_file_path=reg_path,
        )
        db.add(tr)
        db.flush()
        tr_volumes = form.getlist("tr_volume") if hasattr(form, "getlist") else []
        tr_docnums = form.getlist("tr_docnum") if hasattr(form, "getlist") else []
        tr_dates = form.getlist("tr_date") if hasattr(form, "getlist") else []
        tr_companies = form.getlist("tr_company") if hasattr(form, "getlist") else []
        tr_details = form.getlist("tr_details") if hasattr(form, "getlist") else []
        tr_credits = form.getlist("tr_credit") if hasattr(form, "getlist") else []
        tr_cashes = form.getlist("tr_cash") if hasattr(form, "getlist") else []
        for i in range(max(len(tr_volumes), len(tr_details), len(tr_companies))):
            def _s(lst, idx):
                return str(lst[idx]).strip() if idx < len(lst) else ""
            def _amt(lst, idx):
                raw = _s(lst, idx).replace(",", "")
                try:
                    return int(raw) if raw else 0
                except ValueError:
                    return 0
            if not (_s(tr_details, i) or _s(tr_companies, i) or _amt(tr_credits, i) or _amt(tr_cashes, i)):
                continue
            db.add(TripReportLine(
                trip_report_id=tr.id,
                order_no=i + 1,
                volume_no=_s(tr_volumes, i),
                doc_number=_s(tr_docnums, i),
                line_date=_s(tr_dates, i),
                company_name=_s(tr_companies, i),
                details=_s(tr_details, i),
                credit_amount=_amt(tr_credits, i),
                cash_amount=_amt(tr_cashes, i),
            ))
        db.commit()

    return RedirectResponse(url=f"/doc/{d.id}/submit", status_code=303)


@app.get("/doc/{doc_id}/submit", response_class=HTMLResponse)
def doc_submit_get(request: Request, doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "문서를 찾을 수 없습니다.")
    if int(doc.creator_id) != int(user.id) and not bool(user.is_admin):
        raise HTTPException(403, "상신은 작성자만 가능합니다.")
    if str(doc.status) != "DRAFT":
        return RedirectResponse(url=f"/doc/{doc_id}", status_code=303)
    users = db.query(User).filter(User.is_active == True, User.id != user.id).order_by(User.name).all()
    if not users:
        users = db.query(User).filter(User.is_active == True).order_by(User.name).all()
    return templates.TemplateResponse(
        "doc_submit.html",
        {"request": request, "user": user, "doc": doc, "users": users, "doctype_ko": doctype_ko},
    )


@app.post("/doc/{doc_id}/submit")
def doc_submit_post(
    request: Request,
    doc_id: int,
    mode: str = Form("SEQUENTIAL"),
    approver1: str = Form(""),
    approver2: str = Form(""),
    approver3: str = Form(""),
    approver4: str = Form(""),
    approver5: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "문서를 찾을 수 없습니다.")
    if int(doc.creator_id) != int(user.id) and not bool(user.is_admin):
        raise HTTPException(403, "상신은 작성자만 가능합니다.")
    if str(doc.status) != "DRAFT":
        return RedirectResponse(url=f"/doc/{doc_id}", status_code=303)

    raw_ids = [approver1, approver2, approver3, approver4, approver5]
    ids: List[int] = []
    for x in raw_ids:
        s = str(x or "").strip()
        if not s:
            continue
        try:
            uid = int(s)
        except ValueError:
            continue
        if uid not in ids:
            ids.append(uid)

    clean_ids: List[int] = []
    for uid in ids:
        u = db.query(User).filter(User.id == uid, User.is_active == True).first()
        if u and uid not in clean_ids:
            clean_ids.append(uid)

    if not clean_ids:
        return templates.TemplateResponse(
            "doc_submit.html",
            {"request": request, "user": user, "doc": doc, "users": db.query(User).filter(User.is_active == True).order_by(User.name).all(), "doctype_ko": doctype_ko, "error": "결재자를 1명 이상 선택하세요."},
            status_code=400,
        )

    mode = "PARALLEL" if str(mode).upper() == "PARALLEL" else "SEQUENTIAL"
    doc.mode = mode

    db.query(Approver).filter(Approver.doc_id == doc.id).delete()
    for i, uid in enumerate(clean_ids, start=1):
        action = "WAITING"
        if mode == "PARALLEL":
            action = "PENDING"
        elif mode == "SEQUENTIAL" and i == 1:
            action = "PENDING"
        db.add(Approver(doc_id=doc.id, approver_id=uid, order_no=i, action=action))

    doc.status = "IN_REVIEW"
    db.add(EventLog(doc_id=doc.id, user_id=user.id, event="SUBMIT", note=f"상신 mode={mode}"))

    for uid in clean_ids:
        if mode == "PARALLEL" or uid == clean_ids[0]:
            _notify(db, uid, f"[결재요청] {user.name}님이 「{doc.title}」을(를) 상신했습니다", f"/doc/{doc.id}")

    db.commit()

    return RedirectResponse(url=f"/doc/{doc.id}", status_code=303)


@app.get("/doc/{doc_id}/pdf")
def doc_pdf(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "문서를 찾을 수 없습니다.")
    if not can_view_doc(user, doc, db):
        raise HTTPException(403, "열람 권한이 없습니다.")
    if is_doc_final(str(doc.status)):
        _generate_final_pdf(db, doc)
    final_path = os.path.join(DATA_DIR, 'final', f"final_{doc.id}.pdf")
    if not os.path.isfile(final_path):
        raise HTTPException(404, "PDF 파일이 존재하지 않습니다. 결재 완료 후 이용 가능합니다.")
    return FileResponse(final_path, media_type="application/pdf", filename=f"{doc.title or 'document'}_{doc.id}.pdf")


@app.get("/file/original/{doc_id}")
def file_original(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc or not can_view_doc(user, doc, db):
        raise HTTPException(403, "권한이 없습니다.")
    att = _first_attachment(db, doc_id)
    if not att or not os.path.isfile(att.filepath):
        raise HTTPException(404, "원본 파일이 없습니다. 문서 작성 시 첨부해 주세요.")
    return FileResponse(att.filepath, filename=att.filename, media_type=_guess_media_type(att.filepath))


@app.get("/preview/original/{doc_id}")
def preview_original(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc or not can_view_doc(user, doc, db):
        raise HTTPException(403, "권한이 없습니다.")
    att = _first_attachment(db, doc_id)
    if not att or not os.path.isfile(att.filepath):
        return HTMLResponse(
            "<!doctype html><html><body style='font-family:sans-serif;padding:24px;color:#555'>등록된 원본 첨부가 없습니다. "
            "PDF 또는 이미지를 첨부한 뒤 다시 확인해 주세요.</body></html>"
        )
    return FileResponse(
        att.filepath,
        media_type=_guess_media_type(att.filepath),
        headers={"Content-Disposition": f'inline; filename="{att.filename}"'},
    )


_EVENT_KO = {
    "SUBMIT": "상신",
    "APPROVED": "승인",
    "REJECTED": "반려",
    "CREATE": "작성",
}


def _history_pdf_bytes(db: Session, doc: Document) -> bytes:
    events = []
    logs = db.query(EventLog).filter(EventLog.doc_id == doc.id).order_by(EventLog.created_at.asc()).all()
    for ev in logs:
        u = db.get(User, ev.user_id)
        ev_code = ev.event or ""
        events.append({
            "at": _fmt_acted_at_pdf(ev.created_at) if ev.created_at else "",
            "event": _EVENT_KO.get(ev_code, ev_code),
            "user_name": (u.name if u else ""),
            "note": ev.note or "",
        })
    return _render_pdf_html(
        "pdf/history.html",
        {
            "doc": doc,
            "approvers": _fetch_approved_approvers_for_pdf(db, doc.id),
            "events": events,
        },
    )


@app.get("/preview/history/{doc_id}")
def preview_history(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc or not can_view_doc(user, doc, db):
        raise HTTPException(403, "권한이 없습니다.")
    if not is_doc_final(str(doc.status)):
        raise HTTPException(400, "완료된 문서만 조회할 수 있습니다.")
    data = _history_pdf_bytes(db, doc)
    return Response(content=data, media_type="application/pdf", headers={"Content-Disposition": "inline; filename=history.pdf"})


@app.get("/file/history/{doc_id}")
def file_history(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc or not can_view_doc(user, doc, db):
        raise HTTPException(403, "권한이 없습니다.")
    if not is_doc_final(str(doc.status)):
        raise HTTPException(400, "완료된 문서만 다운로드할 수 있습니다.")
    data = _history_pdf_bytes(db, doc)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="history_{doc.id}.pdf"'},
    )


def _perform_single_approve(db: Session, user: User, doc: Document) -> Tuple[bool, str]:
    if str(doc.status) != "IN_REVIEW":
        return False, "not_pending"
    if bool(getattr(user, 'is_admin', False)):
        my_ap = (
            db.query(Approver)
            .filter(Approver.doc_id == doc.id, Approver.action == "PENDING")
            .order_by(Approver.order_no.asc())
            .first()
        )
        if not my_ap:
            return False, "not_pending"
    else:
        if not can_approve_doc(user, doc, db):
            return False, "no_permission"
        allowed_ids = [user.id] + [d.id for d in db.query(User).filter(User.delegate_id == user.id).all()]
        my_ap = (
            db.query(Approver)
            .filter(Approver.doc_id == doc.id, Approver.approver_id.in_(allowed_ids), Approver.action == "PENDING")
            .order_by(Approver.order_no.asc())
            .first()
        )
        if not my_ap:
            return False, "not_pending"
    my_ap.action = "APPROVED"
    my_ap.acted_at = now()
    db.add(EventLog(doc_id=doc.id, user_id=user.id, event="APPROVED", note=f"승인: {user.name}"))
    if str(doc.mode) == "SEQUENTIAL":
        nxt = (
            db.query(Approver)
            .filter(Approver.doc_id == doc.id, Approver.action == "WAITING")
            .order_by(Approver.order_no.asc())
            .first()
        )
        if nxt:
            nxt.action = "PENDING"
            _notify(db, nxt.approver_id, f"[결재요청] 「{doc.title}」 결재 차례입니다", f"/doc/{doc.id}")
    update_doc_status_after_action(db, doc)
    db.refresh(doc)
    if is_doc_final(str(doc.status)):
        _generate_final_pdf(db, doc)
        _notify(db, doc.creator_id, f"[승인완료] 「{doc.title}」이(가) 최종 승인되었습니다", f"/doc/{doc.id}")
    else:
        _notify(db, doc.creator_id, f"[승인] {user.name}님이 「{doc.title}」을(를) 승인했습니다", f"/doc/{doc.id}")
    return True, "ok"


@app.post("/doc/batch_approve")
async def doc_batch_approve(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    form = await request.form()
    raw = form.getlist("doc_ids") if hasattr(form, "getlist") else []
    ok = 0
    for x in raw:
        try:
            did = int(x)
        except (TypeError, ValueError):
            continue
        doc = db.query(Document).filter(Document.id == did).first()
        if not doc:
            continue
        success, _ = _perform_single_approve(db, user, doc)
        if success:
            ok += 1
    resp = RedirectResponse(url="/dashboard", status_code=303)
    resp.set_cookie("flash", f"일괄 승인 처리: {ok}건", max_age=30, httponly=False, samesite="lax")
    return resp


@app.get("/doc/{doc_id}", response_class=HTMLResponse)
def doc_view(request: Request, doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = (
        db.query(Document)
        .options(joinedload(Document.attachments).joinedload(Attachment.uploader))
        .filter(Document.id == doc_id)
        .first()
    )
    if not doc:
        raise HTTPException(404, "문서를 찾을 수 없습니다.")
    if not can_view_doc(user, doc, db):
        raise HTTPException(403, "열람 권한이 없습니다.")
    submitter = db.get(User, doc.creator_id)
    approvers = []
    for a in db.query(Approver).filter(Approver.doc_id == doc.id).order_by(Approver.order_no).all():
        approvers.append({"seq": a.order_no, "user": db.get(User, a.approver_id), "action": a.action, "acted_at": a.acted_at})
    can_act = can_approve_doc(user, doc, db)

    worklog = None
    trip_report = None
    trip_credit_total = 0
    trip_cash_total = 0
    if str(doc.doc_type) == "WORK_LOG":
        worklog = (
            db.query(WorkLog)
            .options(selectinload(WorkLog.lines))
            .filter(WorkLog.doc_id == doc.id)
            .first()
        )
    elif str(doc.doc_type) == "TRIP_REPORT":
        trip_report = (
            db.query(TripReport)
            .options(
                joinedload(TripReport.region),
                selectinload(TripReport.lines),
            )
            .filter(TripReport.doc_id == doc.id)
            .first()
        )
        if trip_report and trip_report.lines:
            trip_credit_total = sum(int(ln.credit_amount or 0) for ln in trip_report.lines)
            trip_cash_total = sum(int(ln.cash_amount or 0) for ln in trip_report.lines)

    return templates.TemplateResponse(
        "doc.html",
        {
            "request": request, "user": user, "doc": doc,
            "submitter": submitter, "approvers": approvers, "can_act": can_act,
            "worklog": worklog, "trip_report": trip_report,
            "trip_credit_total": trip_credit_total,
            "trip_cash_total": trip_cash_total,
        },
    )



@app.post("/doc/{doc_id}/approve")
def doc_approve(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "문서를 찾을 수 없습니다.")
    ok, reason = _perform_single_approve(db, user, doc)
    if not ok:
        if reason == "no_permission":
            raise HTTPException(403, "결재 권한이 없습니다.")
        raise HTTPException(400, "현재 결재할 차례가 아닙니다.")
    return RedirectResponse(url=f"/doc/{doc.id}", status_code=303)



@app.post("/doc/{doc_id}/reject")
def doc_reject(doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "문서를 찾을 수 없습니다.")
    if not can_approve_doc(user, doc, db):
        raise HTTPException(403, "결재 권한이 없습니다.")

    if bool(getattr(user, 'is_admin', False)):
        my_ap = (
            db.query(Approver)
            .filter(Approver.doc_id == doc.id, Approver.action == "PENDING")
            .order_by(Approver.order_no.asc())
            .first()
        )
    else:
        allowed_ids = [user.id] + [d.id for d in db.query(User).filter(User.delegate_id == user.id).all()]
        my_ap = (
            db.query(Approver)
            .filter(Approver.doc_id == doc.id, Approver.approver_id.in_(allowed_ids), Approver.action == "PENDING")
            .order_by(Approver.order_no.asc())
            .first()
        )
    if not my_ap:
        raise HTTPException(400, "현재 결재할 차례가 아닙니다.")

    my_ap.action = "REJECTED"
    my_ap.acted_at = now()
    db.add(EventLog(doc_id=doc.id, user_id=user.id, event="REJECTED", note=f"반려: {user.name}"))
    setattr(doc, 'status', "REJECTED")
    _notify(db, doc.creator_id, f"[반려] {user.name}님이 「{doc.title}」을(를) 반려했습니다", f"/doc/{doc.id}")
    db.commit()
    return RedirectResponse(url=f"/doc/{doc.id}", status_code=303)

# change-password: Flask 스타일을 FastAPI GET/POST로 변환
@app.get("/change-password", response_class=HTMLResponse)
def change_password_get(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse("change_password.html", {"request": request, "user": user})


@app.post("/change-password")
def change_password_post(
    current_pw: str = Form(...),
    new_pw: str = Form(...),
    new_pw2: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not verify_pw(current_pw, str(user.password_hash)):
        raise HTTPException(400, "현재 비밀번호가 틀립니다.")
    if new_pw != new_pw2 or len(new_pw) < 6:
        raise HTTPException(400, "새 비밀번호가 일치하지 않거나 너무 짧습니다.")
    user.password_hash = hash_pw(new_pw)
    user.must_change_pw = False
    db.commit()
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    docs = sorted(visible_docs(db, user), key=lambda d: d.updated_at or d.created_at, reverse=True)
    approvable_docs = [d.id for d in docs if d.status == "IN_REVIEW" and can_approve_doc(user, d, db)]
    resp = templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": user, "docs": docs, "approvable_docs": approvable_docs, "flash": request.cookies.get("flash")},
    )
    return resp

# ... additional GET routes for templates (render with minimal context) ...

@app.get("/boards", response_class=HTMLResponse)
def boards_list(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    boards = db.query(Board).order_by(Board.created_at).all()
    recent_posts = db.query(Post).order_by(Post.created_at.desc()).limit(10).all()
    return templates.TemplateResponse("board_list_all.html", {"request": request, "user": user, "boards": boards, "recent_posts": recent_posts})


@app.get("/board/{board_id}", response_class=HTMLResponse)
def board_view_route(request: Request, board_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    board = db.query(Board).get(board_id)
    if not board:
        raise HTTPException(404, "게시판을 찾을 수 없습니다.")
    posts = db.query(Post).filter(Post.board_id == board.id).order_by(Post.created_at.desc()).all()
    return templates.TemplateResponse("board_view.html", {"request": request, "user": user, "board": board, "posts": posts})


@app.get("/board/{board_id}/new", response_class=HTMLResponse)
def board_new(request: Request, board_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    board = db.query(Board).get(board_id)
    if not board:
        raise HTTPException(404, "게시판을 찾을 수 없습니다.")
    return templates.TemplateResponse("board_new.html", {"request": request, "user": user, "board": board})


@app.post("/board/{board_id}/new")
def board_new_post(
    board_id: int,
    request: Request,
    title: str = Form(...),
    content: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    board = db.query(Board).get(board_id)
    if not board:
        raise HTTPException(404, "게시판을 찾을 수 없습니다.")
    
    post = Post(board_id=board.id, user_id=user.id, title=title.strip(), content=content.strip())
    db.add(post)
    db.commit()
    db.refresh(post)

    if "공지" in board.name:
        active_users = db.query(User).filter(User.is_active == True, User.id != user.id).all()
        for u in active_users:
            _notify(db, u.id, f"[{board.name}] {post.title}", f"/post/{post.id}")
        db.commit()

    return RedirectResponse(url=f"/board/{board.id}", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin_index(_: User = Depends(require_admin)):
    return RedirectResponse(url="/admin/users", status_code=303)


@app.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    grades = db.query(Grade).filter(Grade.is_active == True).order_by(Grade.name).all()
    users = db.query(User).order_by(User.id).all()
    flash = request.query_params.get("flash", "")
    return templates.TemplateResponse(
        "admin_users.html",
        {"request": request, "user": user, "grades": grades, "users": users, "flash": flash},
    )


@app.post("/admin/users/add")
async def admin_users_add(
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    form = await request.form()
    username = str(form.get("username") or "").strip()
    name = str(form.get("name") or "").strip()
    dept = str(form.get("dept") or "").strip()
    temp_pw = str(form.get("temp_pw") or ADMIN_DEFAULT_PW).strip() or ADMIN_DEFAULT_PW
    grade_name = _resolve_user_grade(db, str(form.get("grade_id") or ""), str(form.get("grade") or ""))
    is_admin = _is_truthy_admin(form.get("is_admin"))

    if not username or not name:
        return _admin_redirect_users("아이디와 이름은 필수입니다.")
    if db.query(User).filter(User.username == username).first():
        return _admin_redirect_users(f"이미 존재하는 아이디입니다: {username}")

    u = User(
        username=username,
        name=name,
        dept=dept,
        grade=grade_name,
        is_admin=is_admin,
        is_active=True,
        password_hash=hash_pw(temp_pw),
        must_change_pw=True,
    )
    db.add(u)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _admin_redirect_users("사용자 등록에 실패했습니다.")
    return _admin_redirect_users(f"사용자 '{username}' 을(를) 등록했습니다.")


@app.post("/admin/users/import_csv")
async def admin_users_import_csv(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    file: UploadFile = File(...),
):
    raw = await file.read()
    if not raw:
        return _admin_redirect_users("CSV 파일이 비어 있습니다.")

    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            text = None
    if text is None:
        return _admin_redirect_users("CSV 인코딩을 읽을 수 없습니다. UTF-8로 저장해 주세요.")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return _admin_redirect_users("CSV 헤더가 없습니다.")

    norm = {(h or "").strip().lower(): h for h in reader.fieldnames}
    need = ["username", "name"]
    for col in need:
        if col not in norm:
            return _admin_redirect_users(f"CSV에 '{col}' 컬럼이 필요합니다.")

    created = skipped = 0
    for row in reader:
        username = str(row.get(norm["username"]) or "").strip()
        name = str(row.get(norm["name"]) or "").strip()
        if not username or not name:
            continue
        if db.query(User).filter(User.username == username).first():
            skipped += 1
            continue
        dept = str(row.get(norm.get("dept", ""), "") or "").strip() if "dept" in norm else ""
        grade_cell = str(row.get(norm.get("grade", ""), "") or "").strip() if "grade" in norm else ""
        grade_name = _lookup_grade_name(db, grade_cell)
        is_admin = False
        if "is_admin" in norm:
            is_admin = _is_truthy_admin(row.get(norm["is_admin"]))

        db.add(
            User(
                username=username,
                name=name,
                dept=dept,
                grade=grade_name,
                is_admin=is_admin,
                is_active=True,
                password_hash=hash_pw(ADMIN_DEFAULT_PW),
                must_change_pw=True,
            )
        )
        created += 1

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _admin_redirect_users("CSV 등록 중 오류가 발생했습니다.")

    return _admin_redirect_users(f"CSV 등록 완료: 신규 {created}명, 건너뜀 {skipped}명")


@app.post("/admin/users/reset_pw")
async def admin_users_reset_pw(
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    form = await request.form()
    try:
        user_id = int(form.get("user_id") or 0)
    except (TypeError, ValueError):
        user_id = 0
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return _admin_redirect_users("사용자를 찾을 수 없습니다.")
    target.password_hash = hash_pw(ADMIN_DEFAULT_PW)
    target.must_change_pw = True
    db.commit()
    return _admin_redirect_users(f"'{target.username}' 비밀번호를 초기화했습니다. ({ADMIN_DEFAULT_PW})")


@app.post("/admin/users/{user_id}/delete")
def admin_users_delete(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return _admin_redirect_users("사용자를 찾을 수 없습니다.")
    if target.id == admin.id:
        return _admin_redirect_users("본인 계정은 비활성화할 수 없습니다.")
    if target.username == ADMIN_ID:
        return _admin_redirect_users("기본 관리자 계정은 비활성화할 수 없습니다.")
    if target.is_admin and _count_active_admins(db, exclude_user_id=target.id) < 1:
        return _admin_redirect_users("마지막 관리자는 비활성화할 수 없습니다.")

    target.is_active = False
    db.commit()
    return _admin_redirect_users(f"'{target.username}' 계정을 비활성화했습니다.")


@app.get("/admin/users/{user_id}/edit", response_class=HTMLResponse)
def admin_user_edit_get(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404, "사용자를 찾을 수 없습니다.")
    grades = db.query(Grade).filter(Grade.is_active == True).order_by(Grade.name).all()
    return templates.TemplateResponse(
        "admin_user_edit.html",
        {"request": request, "user": user, "u": u, "grades": grades},
    )


@app.post("/admin/users/{user_id}/edit")
async def admin_user_edit_post(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return _admin_redirect_users("사용자를 찾을 수 없습니다.")

    form = await request.form()
    name = str(form.get("name") or "").strip()
    if not name:
        return _admin_redirect_users("이름은 필수입니다.")

    new_is_admin = _is_truthy_admin(form.get("is_admin"))
    new_is_active = str(form.get("is_active") or "1").strip() == "1"

    if target.is_admin and not new_is_admin and _count_active_admins(db, exclude_user_id=target.id) < 1:
        return _admin_redirect_users("마지막 관리자의 권한은 해제할 수 없습니다.")
    if not new_is_active and target.id == admin.id:
        return _admin_redirect_users("본인 계정은 비활성화할 수 없습니다.")
    if not new_is_active and target.is_admin and _count_active_admins(db, exclude_user_id=target.id) < 1:
        return _admin_redirect_users("마지막 관리자는 비활성화할 수 없습니다.")

    target.name = name
    target.dept = str(form.get("dept") or "").strip()
    target.grade = _resolve_user_grade(db, str(form.get("grade_id") or ""), str(form.get("grade") or ""))
    target.is_admin = new_is_admin
    target.is_active = new_is_active
    target.must_change_pw = str(form.get("must_change_pw") or "0").strip() == "1"

    new_pw = str(form.get("new_pw") or "").strip()
    if new_pw:
        target.password_hash = hash_pw(new_pw)
        target.must_change_pw = True

    db.commit()
    return _admin_redirect_users(f"'{target.username}' 정보를 저장했습니다.")


@app.get("/admin/grades", response_class=HTMLResponse)
def admin_grades(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    grades = db.query(Grade).order_by(Grade.id).all()
    flash = request.query_params.get("flash", "")
    return templates.TemplateResponse(
        "admin_grades.html",
        {"request": request, "user": user, "grades": grades, "flash": flash},
    )


@app.post("/admin/grades/add")
async def admin_grades_add(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    name: str = Form(...),
):
    name = (name or "").strip()
    if not name:
        return _admin_redirect_grades("직급명을 입력하세요.")
    if db.query(Grade).filter(Grade.name == name).first():
        return _admin_redirect_grades(f"이미 있는 직급입니다: {name}")
    db.add(Grade(name=name, is_active=True))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _admin_redirect_grades("직급 등록에 실패했습니다.")
    return _admin_redirect_grades(f"직급 '{name}' 을(를) 등록했습니다.")


@app.post("/admin/grades/{grade_id}/delete")
def admin_grades_delete(
    grade_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    g = db.query(Grade).filter(Grade.id == grade_id).first()
    if not g:
        return _admin_redirect_grades("직급을 찾을 수 없습니다.")
    g.is_active = False
    for u in db.query(User).filter(User.grade == g.name).all():
        u.grade = ""
    db.commit()
    return _admin_redirect_grades(f"직급 '{g.name}' 을(를) 비활성화했습니다.")


@app.post("/admin/grades/{grade_id}/restore")
def admin_grades_restore(
    grade_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    g = db.query(Grade).filter(Grade.id == grade_id).first()
    if not g:
        return _admin_redirect_grades("직급을 찾을 수 없습니다.")
    g.is_active = True
    db.commit()
    return _admin_redirect_grades(f"직급 '{g.name}' 을(를) 복구했습니다.")


@app.get("/my_profile", response_class=HTMLResponse)
def my_profile(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse("my_profile.html", {"request": request, "user": user})


@app.get("/messages", response_class=HTMLResponse)
def messages_list(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    load_opts = joinedload(Message.sender), joinedload(Message.receiver), joinedload(Message.attachments)
    inbox = (
        db.query(Message)
        .options(*load_opts)
        .filter(Message.receiver_id == user.id)
        .order_by(Message.created_at.desc())
        .all()
    )
    outbox = (
        db.query(Message)
        .options(*load_opts)
        .filter(Message.sender_id == user.id)
        .order_by(Message.created_at.desc())
        .all()
    )
    users = db.query(User).filter(User.is_active == True, User.id != user.id).order_by(User.name).all()
    return templates.TemplateResponse("messages.html", {
        "request": request, "user": user,
        "inbox": inbox, "outbox": outbox, "users": users,
    })


@app.post("/messages/new")
async def messages_new(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    form = await request.form()
    try:
        receiver_id = int(form.get("receiver_id") or 0)
    except (TypeError, ValueError):
        receiver_id = 0
    content = str(form.get("content") or "").strip()
    if not receiver_id:
        return RedirectResponse(url="/messages", status_code=303)
    receiver = db.query(User).get(receiver_id)
    if not receiver:
        return RedirectResponse(url="/messages", status_code=303)
    upload_files = form.getlist("files") if hasattr(form, "getlist") else []
    has_files = any(isinstance(f, UploadFile) and f.filename for f in upload_files)
    if not content and not has_files:
        return RedirectResponse(url="/messages", status_code=303)
    msg = Message(sender_id=user.id, receiver_id=receiver_id, content=content or "(첨부파일)")
    db.add(msg)
    db.flush()
    await _save_message_attachments(db, msg.id, user.id, form)
    _notify(db, receiver_id, f"[쪽지] {user.name}님이 쪽지를 보냈습니다", f"/messages/{msg.id}")
    db.commit()
    return RedirectResponse(url="/messages", status_code=303)


def _render_message_view(request: Request, msg_id: int, db: Session, user: User):
    m = (
        db.query(Message)
        .options(
            joinedload(Message.sender),
            joinedload(Message.receiver),
            joinedload(Message.attachments),
        )
        .filter(Message.id == msg_id)
        .first()
    )
    if not m or not _can_view_message(user, m):
        raise HTTPException(404, "메시지를 찾을 수 없습니다.")
    if m.receiver_id == user.id and not m.read_at:
        m.read_at = now()
        db.commit()
        db.refresh(m)
    return templates.TemplateResponse("message_view.html", {"request": request, "user": user, "msg": m})


@app.get("/messages/{msg_id}", response_class=HTMLResponse)
def messages_view(request: Request, msg_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _render_message_view(request, msg_id, db, user)


@app.get("/message/{msg_id}", response_class=HTMLResponse)
def message_view(request: Request, msg_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _render_message_view(request, msg_id, db, user)


@app.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    notes = db.query(Notification).filter(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(100).all()
    db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read == False).update({"is_read": True})
    db.commit()
    return templates.TemplateResponse("notifications.html", {"request": request, "user": user, "notis": notes})


@app.get("/quality", response_class=HTMLResponse)
def quality_list(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    docs = db.query(Document).filter(Document.doc_type == "QUALITY").order_by(Document.created_at.desc()).all()
    return templates.TemplateResponse("quality_list.html", {"request": request, "user": user, "docs": docs})


@app.get("/quality/doc/{doc_id}", response_class=HTMLResponse)
def quality_doc(request: Request, doc_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc = db.query(Document).get(doc_id)
    if not doc:
        raise HTTPException(404, "문서를 찾을 수 없습니다.")
    return templates.TemplateResponse("quality_doc.html", {"request": request, "user": user, "doc": doc})


# ------------------------------------------------------------
# Phase 4: 품질문서 NAS 라이브러리
# ------------------------------------------------------------
import quality_fs as _qfs

@app.get("/quality/library", response_class=HTMLResponse)
def quality_library(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tree = _qfs.scan_tree()
    quality_docs = db.query(QualityDoc).order_by(QualityDoc.updated_at.desc()).limit(50).all()
    return templates.TemplateResponse("quality_library.html", {
        "request": request, "user": user,
        "tree": tree,
        "quality_docs": quality_docs,
    })


@app.get("/quality/file/view")
def quality_file_view(request: Request, path: str = "", db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    abs_path = _qfs.resolve_file_path(path)
    if not abs_path or not os.path.isfile(abs_path):
        raise HTTPException(404, "파일을 찾을 수 없습니다.")
    ext = os.path.splitext(abs_path)[1].lower()
    fname = os.path.basename(abs_path)
    from urllib.parse import quote
    encoded_name = quote(fname)
    if _qfs.can_inline_view(ext):
        cd = f"inline; filename*=UTF-8''{encoded_name}"
        return FileResponse(abs_path, media_type=_guess_media_type(abs_path),
                            headers={"Content-Disposition": cd})
    if _qfs.can_download(ext):
        cd = f"attachment; filename*=UTF-8''{encoded_name}"
        return FileResponse(abs_path, media_type="application/octet-stream",
                            headers={"Content-Disposition": cd})
    raise HTTPException(400, "지원하지 않는 파일 형식입니다.")


@app.get("/quality/file/download")
def quality_file_download(request: Request, path: str = "", db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    abs_path = _qfs.resolve_file_path(path)
    if not abs_path or not os.path.isfile(abs_path):
        raise HTTPException(404, "파일을 찾을 수 없습니다.")
    from urllib.parse import quote
    fname = os.path.basename(abs_path)
    cd = f"attachment; filename*=UTF-8''{quote(fname)}"
    return FileResponse(abs_path, media_type="application/octet-stream",
                        headers={"Content-Disposition": cd})


@app.post("/quality/revise")
async def quality_revise(
    request: Request,
    doc_no: str = Form(""),
    title: str = Form(""),
    original_path: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    file: UploadFile = File(None),
):
    """재개정 상신: 새 파일 업로드 → QUALITY Document 생성 → 결재선 페이지로 이동"""
    if not title.strip():
        title = f"[품질문서 개정] {doc_no}" if doc_no else "[품질문서 개정]"

    prev_qd = db.query(QualityDoc).filter(QualityDoc.doc_no == doc_no).order_by(QualityDoc.rev_no.desc()).first()
    new_rev = (prev_qd.rev_no + 1) if prev_qd else 1

    d = Document(
        title=title.strip(),
        body=f"품질문서 재개정 (Rev.{new_rev})\n원본 경로: {original_path}",
        creator_id=user.id,
        doc_type="QUALITY",
        doc_no=doc_no,
        rev=new_rev,
        status="DRAFT",
    )
    db.add(d)
    db.commit()
    db.refresh(d)

    file_path = ""
    if file and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        if not _qfs.can_download(ext):
            raise HTTPException(400, f"허용되지 않는 파일 형식입니다: {ext}")
        
        upload_dir = os.path.join(DATA_DIR, "uploads", str(d.id))
        os.makedirs(upload_dir, exist_ok=True)
        fname = f"{uuid.uuid4().hex}_{file.filename}"
        fpath = os.path.join(upload_dir, fname)
        with open(fpath, "wb") as out:
            content = await file.read()
            out.write(content)
        db.add(Attachment(doc_id=d.id, uploader_id=user.id, filename=file.filename, filepath=fpath, filesize=len(content)))
        file_path = fpath
        db.commit()

    qd = QualityDoc(
        doc_no=doc_no,
        title=title.strip(),
        rev_no=new_rev,
        file_path=file_path or original_path,
        original_filename=file.filename if (file and file.filename) else "",
        document_id=d.id,
        uploader_id=user.id,
        status="PENDING",
    )
    db.add(qd)
    db.commit()

    return RedirectResponse(url=f"/doc/{d.id}/submit", status_code=303)


# ── Phase 4-v2: 문서별 이력 조회 API ──

@app.get("/api/quality/history")
def api_quality_history(
    request: Request,
    doc_no: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """특정 문서번호의 전체 리비전 이력을 JSON으로 반환"""
    if not doc_no.strip():
        return {"items": []}
    revisions = (
        db.query(QualityDoc)
        .filter(QualityDoc.doc_no == doc_no.strip())
        .order_by(QualityDoc.rev_no.desc())
        .all()
    )
    items = []
    for r in revisions:
        att = None
        if r.document_id:
            att = db.query(Attachment).filter(Attachment.doc_id == r.document_id).order_by(Attachment.id.desc()).first()
        items.append({
            "id": r.id,
            "doc_no": r.doc_no,
            "title": r.title,
            "rev_no": r.rev_no,
            "status": r.status,
            "original_filename": r.original_filename or (att.filename if att else ""),
            "has_pdf": bool(r.file_path and r.file_path.lower().endswith(".pdf")),
            "file_path": r.file_path or "",
            "archive_path": r.archive_path or "",
            "has_archive": bool(r.archive_path and os.path.isfile(r.archive_path)),
            "document_id": r.document_id,
            "uploader": r.uploader.name if r.uploader else "",
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
            "updated_at": r.updated_at.strftime("%Y-%m-%d") if r.updated_at else "",
        })
    return {"items": items}


@app.get("/api/quality/search")
def api_quality_search(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """문서번호 또는 제목으로 품질문서 그룹 검색 → 중복 제거된 doc_no 목록"""
    if not q.strip():
        return {"groups": []}
    query = q.strip()
    rows = (
        db.query(QualityDoc.doc_no, QualityDoc.title)
        .filter(
            (QualityDoc.doc_no.ilike(f"%{query}%")) | (QualityDoc.title.ilike(f"%{query}%"))
        )
        .all()
    )
    seen = {}
    for r in rows:
        if r.doc_no not in seen:
            seen[r.doc_no] = r.title
    return {"groups": [{"doc_no": k, "title": v} for k, v in seen.items()]}


@app.get("/quality/archive/download")
def quality_archive_download(
    request: Request,
    qd_id: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """아카이빙된 원본 파일 다운로드 (archive_path 또는 Attachment)"""
    qd = db.query(QualityDoc).get(qd_id)
    if not qd:
        raise HTTPException(404, "이력을 찾을 수 없습니다.")
    fpath = qd.archive_path
    if fpath and os.path.isfile(fpath):
        from urllib.parse import quote
        cd = f"attachment; filename*=UTF-8''{quote(os.path.basename(fpath))}"
        return FileResponse(fpath, media_type="application/octet-stream", headers={"Content-Disposition": cd})
    if qd.document_id:
        att = db.query(Attachment).filter(Attachment.doc_id == qd.document_id).order_by(Attachment.id.desc()).first()
        if att and os.path.isfile(att.filepath):
            from urllib.parse import quote
            cd = f"attachment; filename*=UTF-8''{quote(att.filename)}"
            return FileResponse(att.filepath, media_type="application/octet-stream", headers={"Content-Disposition": cd})
    raise HTTPException(404, "파일을 찾을 수 없습니다.")


@app.get("/quality/revision/pdf")
def quality_revision_pdf(
    request: Request,
    qd_id: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """리비전의 PDF 파일을 인라인 반환 (PDF 뷰어용)"""
    qd = db.query(QualityDoc).get(qd_id)
    if not qd:
        raise HTTPException(404, "이력을 찾을 수 없습니다.")
    pdf_path = qd.file_path
    if pdf_path and pdf_path.lower().endswith(".pdf") and os.path.isfile(pdf_path):
        from urllib.parse import quote
        cd = f"inline; filename*=UTF-8''{quote(os.path.basename(pdf_path))}"
        return FileResponse(pdf_path, media_type="application/pdf", headers={"Content-Disposition": cd})
    if qd.document_id:
        att = db.query(Attachment).filter(
            Attachment.doc_id == qd.document_id,
            Attachment.filename.ilike("%.pdf"),
        ).first()
        if att and os.path.isfile(att.filepath):
            from urllib.parse import quote
            cd = f"inline; filename*=UTF-8''{quote(att.filename)}"
            return FileResponse(att.filepath, media_type="application/pdf", headers={"Content-Disposition": cd})
    raise HTTPException(404, "PDF 파일이 없습니다.")


@app.get("/completed", response_class=HTMLResponse)
def completed(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    doc_no = request.query_params.get("doc_no", "").strip()
    title_q = request.query_params.get("title", "").strip()
    submitter = request.query_params.get("submitter", "").strip()
    start = request.query_params.get("start", "").strip()
    end = request.query_params.get("end", "").strip()
    docs_query = db.query(Document).filter(Document.status.in_(DOC_FINAL_STATUSES))
    # 개별 필드 검색 우선 적용
    if doc_no:
        docs_query = docs_query.filter(Document.doc_no.contains(doc_no))
    if title_q:
        docs_query = docs_query.filter(Document.title.contains(title_q))
    if submitter:
        docs_query = docs_query.join(User, Document.creator_id == User.id).filter(User.name.contains(submitter))
    if start:
        try:
            start_dt = datetime.fromisoformat(start)
            docs_query = docs_query.filter(Document.created_at >= start_dt)
        except Exception:
            pass
    if end:
        try:
            end_dt = datetime.fromisoformat(end) + timedelta(days=1)
            docs_query = docs_query.filter(Document.created_at < end_dt)
        except Exception:
            pass
    docs = docs_query.order_by(Document.created_at.desc()).all()
    # 템플릿이 기대하는 추가 속성(`submitter`, `final_approver`, `final_path`)을 문서 객체에 붙임
    for d in docs:
        try:
            d.submitter = db.query(User).get(d.creator_id)
        except Exception:
            d.submitter = None
        # 마지막으로 승인 처리한 결재자(acted_at 기준)를 가져옴
        try:
            fa = db.query(Approver).filter(Approver.doc_id == d.id, Approver.action == "APPROVED").order_by(Approver.acted_at.desc()).first()
            d.final_approver = db.query(User).get(fa.approver_id) if fa else None
        except Exception:
            d.final_approver = None
        # 추후 PDF 경로 또는 생성 로직이 들어갈 자리
        # final_path 체크: 파일이 존재하면 경로 반환
        fp = os.path.join(DATA_DIR, 'final', f"final_{d.id}.pdf")
        d.final_path = fp if os.path.isfile(fp) else None

    return templates.TemplateResponse("completed.html", {"request": request, "user": user, "docs": docs, "doc_no": doc_no, "title": title_q, "submitter": submitter, "start": start, "end": end})


@app.get("/accounting/dashboard", response_class=HTMLResponse)
def accounting_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    mode, date_from, date_to, ref = _parse_accounting_period(request)
    try:
        total_billing = _sum_trip_billing(db, date_from, date_to)
        total_collection = _sum_collections(db, date_from, date_to)
        receivable_balance = _cumulative_receivable(db, date_to)
        flow_rows = _accounting_flow_rows(db, mode, date_from, date_to)
    except Exception as e:
        print(f"[accounting/dashboard] aggregate failed: {e}")
        import traceback
        traceback.print_exc()
        total_billing = total_collection = 0
        receivable_balance = 0
        flow_rows = []
    period_label = _accounting_period_label(mode, ref, date_from, date_to)
    today = datetime.now()
    flow_headers = {
        "day": ("일자", "당일 요약"),
        "month": ("일자", "일별 자금 흐름"),
        "quarter": ("월", "월별 자금 흐름"),
        "year": ("월", "월별 자금 흐름"),
    }
    bucket_header, flow_title = flow_headers.get(mode, ("기간", "자금 흐름"))
    q_year = today.year
    q_num = (today.month - 1) // 3 + 1
    if mode == "quarter" and "-Q" in ref:
        try:
            q_year = int(ref.split("-Q")[0])
            q_num = int(ref.split("-Q")[1])
        except (ValueError, IndexError):
            pass
    return templates.TemplateResponse(
        "accounting_dashboard.html",
        {
            "request": request,
            "user": user,
            "mode": mode,
            "ref": ref,
            "date_from": date_from,
            "date_to": date_to,
            "period_label": period_label,
            "total_billing": total_billing,
            "total_collection": total_collection,
            "period_net": total_billing - total_collection,
            "receivable_balance": receivable_balance,
            "flow_rows": flow_rows,
            "bucket_header": bucket_header,
            "flow_title": flow_title,
            "filter_year": request.query_params.get("year") or str(q_year),
            "filter_quarter": request.query_params.get("quarter") or str(q_num),
        },
    )


@app.get("/accounting/ledger", response_class=HTMLResponse)
def accounting_ledger(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    month_ref, month_start, month_end = _parse_ledger_month(request)
    region_id_raw = request.query_params.get("region_id", "").strip()
    company_q = request.query_params.get("company", "").strip()
    region_id: Optional[int] = None
    if region_id_raw:
        try:
            region_id = int(region_id_raw)
        except (ValueError, TypeError):
            region_id = None
    try:
        regions = db.query(Region).order_by(Region.name.asc()).all()
    except Exception as e:
        print(f"[ledger] regions query failed: {e}")
        regions = []
    try:
        ledger_rows = _build_ledger_rows(
            db, month_start, month_end, region_id=region_id, company_q=company_q
        )
    except Exception as e:
        print(f"[ledger] _build_ledger_rows failed: {e}")
        import traceback
        traceback.print_exc()
        ledger_rows = []
    totals = {
        "opening": sum(r["opening"] for r in ledger_rows),
        "billing_current": sum(r["billing_current"] for r in ledger_rows),
        "collection_current": sum(r["collection_current"] for r in ledger_rows),
        "balance": sum(r["balance"] for r in ledger_rows),
    }
    return templates.TemplateResponse(
        "accounting_ledger.html",
        {
            "request": request,
            "user": user,
            "month_ref": month_ref,
            "region_id": region_id_raw,
            "company_q": company_q,
            "regions": regions,
            "ledger_rows": ledger_rows,
            "totals": totals,
        },
    )


@app.post("/api/collections")
async def api_collections_create(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    payload: dict = {}
    try:
        payload = await request.json()
    except Exception:
        form = await request.form()
        payload = dict(form)
    company_name = str(payload.get("company_name") or "").strip()
    region_name = str(payload.get("region_name") or "").strip()
    collection_date = str(payload.get("collection_date") or "").strip()[:10]
    note = str(payload.get("note") or "").strip()
    try:
        amount = int(str(payload.get("amount") or "0").replace(",", ""))
    except (TypeError, ValueError):
        amount = 0
    if not company_name or not region_name:
        raise HTTPException(400, "업체명과 지역을 입력하세요.")
    if not collection_date:
        raise HTTPException(400, "수금일을 입력하세요.")
    if amount <= 0:
        raise HTTPException(400, "수금액을 입력하세요.")
    if not db.query(Region).filter(Region.name == region_name).first():
        raise HTTPException(400, "등록되지 않은 지역입니다. 지역 마스터에 먼저 등록하세요.")
    row = Collection(
        company_name=company_name,
        region_name=region_name,
        amount=amount,
        collection_date=collection_date,
        note=note,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "ok": True,
        "id": row.id,
        "company_name": row.company_name,
        "region_name": row.region_name,
        "amount": row.amount,
        "collection_date": row.collection_date,
    }


@app.get("/calendar", response_class=HTMLResponse)
def calendar_view(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return templates.TemplateResponse("calendar.html", {
        "request": request, "user": user, "me": user,
        "schedule_types": SCHEDULE_TYPES,
    })


@app.get("/me", response_class=HTMLResponse)
def me_view(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse("me.html", {"request": request, "user": user})


@app.get("/post/{post_id}", response_class=HTMLResponse)
def post_view(request: Request, post_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    post = db.query(Post).get(post_id)
    if not post:
        raise HTTPException(404, "글을 찾을 수 없습니다.")
    board = db.query(Board).get(post.board_id)
    return templates.TemplateResponse("post_view.html", {"request": request, "user": user, "post": post, "board": board})


@app.get("/org", response_class=HTMLResponse)
def org_chart(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # build org dict by dept
    users = db.query(User).filter(User.is_active == True).order_by(User.dept).all()
    org = {}
    for u in users:
        org.setdefault(u.dept or "기타", []).append(u)
    return templates.TemplateResponse("org_chart.html", {"request": request, "user": user, "org_dict": org, "me": user})


def _notify(db: Session, user_id: int, title: str, link: str = ""):
    """알림 생성 헬퍼"""
    db.add(Notification(user_id=user_id, title=title, link=link))


@app.get("/api/notifications/count")
def api_notifications_count(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read == False).count()
    return {"count": n}


@app.get("/api/notifications/list")
def api_notifications_list(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    notes = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(30)
        .all()
    )
    return {"items": [{
        "id": n.id,
        "title": n.title,
        "link": n.link or "",
        "is_read": bool(n.is_read),
        "created_at": n.created_at.strftime("%m/%d %H:%M") if n.created_at else "",
    } for n in notes]}


@app.post("/api/notifications/read/{noti_id}")
def api_notification_read(noti_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.query(Notification).filter(Notification.id == noti_id, Notification.user_id == user.id).first()
    if n:
        n.is_read = True
        db.commit()
    return {"ok": True}


@app.post("/api/notifications/read_all")
def api_notification_read_all(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read == False).update({"is_read": True})
    db.commit()
    return {"ok": True}


@app.get("/api/events")
def api_events(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    evs = db.query(CalendarEvent).all()
    out = []
    for e in evs:
        out.append({
            "id": e.id,
            "title": e.title,
            "start": e.start_time.isoformat() if e.start_time else None,
            "end": e.end_time.isoformat() if e.end_time else None,
            "allDay": bool(e.is_all_day),
            "user_id": e.user_id,
            "location": e.location,
            "description": e.description,
        })
    return out


@app.post("/api/events")
async def api_events_create(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Support form POST from template: prefer form() or JSON, fallback to query_params
    form_data = {}
    try:
        f = await request.form()
        # Convert Starlette form data to dict
        form_data = {k: v for k, v in f.items()}
    except Exception:
        form_data = {}

    body = None
    try:
        body = await request.json()
    except Exception:
        body = None

    def get_field(name, default=None):
        if form_data and name in form_data:
            return form_data.get(name)
        if body and isinstance(body, dict) and name in body:
            return body.get(name)
        if request.query_params and name in request.query_params:
            return request.query_params.get(name)
        return default

    event_type = get_field('event_type', 'PERSONAL')
    title = get_field('title', '일정')
    start_time = get_field('start_time')
    end_time = get_field('end_time')
    is_all_day = get_field('is_all_day', False)
    location = get_field('location', '')
    description = get_field('description', '')
    try:
        st = datetime.fromisoformat(start_time) if start_time else datetime.now()
    except Exception:
        st = datetime.now()
    try:
        et = datetime.fromisoformat(end_time) if end_time else st
    except Exception:
        et = st
    ev = CalendarEvent(user_id=user.id, title=title, description=description, start_time=st, end_time=et, is_all_day=bool(is_all_day), event_type=event_type, location=location)
    db.add(ev)
    db.commit()
    return RedirectResponse(url="/calendar", status_code=303)


@app.post("/api/events/{event_id}/delete")
def api_events_delete(event_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ev = db.query(CalendarEvent).get(event_id)
    if not ev:
        raise HTTPException(404, "일정을 찾을 수 없습니다.")
    if ev.user_id != user.id and not user.is_admin:
        raise HTTPException(403, "권한이 없습니다.")
    db.delete(ev)
    db.commit()
    return RedirectResponse(url="/calendar", status_code=303)


# ------------------------------------------------------------
# Phase 2: Schedule CRUD API
# ------------------------------------------------------------

SCHEDULE_COLOR_MAP = {
    "LEAVE": "#ef4444",
    "COMPANY": "#2563eb",
    "TEAM_1": "#f59e0b",
    "TEAM_2": "#10b981",
    "TEAM_3": "#8b5cf6",
    "TEAM_4": "#ec4899",
    "TEAM_5": "#06b6d4",
}


@app.get("/api/schedules")
def api_schedules(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """FullCalendar가 사용하는 JSON 이벤트 배열 반환 (Schedule + 레거시 CalendarEvent 통합)"""
    out = []

    # 신규 Schedule 모델
    schedules = db.query(Schedule).filter(Schedule.status == "ACTIVE").all()
    for s in schedules:
        u = db.get(User, s.user_id)
        out.append({
            "id": f"sch_{s.id}",
            "title": s.title,
            "start": s.start_date,
            "end": s.end_date,
            "allDay": True,
            "color": s.color or SCHEDULE_COLOR_MAP.get(s.schedule_type, "#6b7280"),
            "extendedProps": {
                "source": "schedule",
                "schedule_id": s.id,
                "schedule_type": s.schedule_type,
                "schedule_type_ko": schedule_type_ko(s.schedule_type),
                "user_id": s.user_id,
                "user_name": u.name if u else "",
                "memo": s.memo or "",
                "document_id": s.document_id,
                "editable": (s.user_id == user.id or bool(user.is_admin)) and s.document_id is None,
            },
        })

    # 레거시 CalendarEvent (Schedule과 중복되지 않는 것만)
    legacy = db.query(CalendarEvent).all()
    for e in legacy:
        out.append({
            "id": f"evt_{e.id}",
            "title": e.title,
            "start": e.start_time.isoformat() if e.start_time else None,
            "end": e.end_time.isoformat() if e.end_time else None,
            "allDay": bool(e.is_all_day),
            "color": "#6b7280",
            "extendedProps": {
                "source": "calendar_event",
                "event_id": e.id,
                "user_id": e.user_id,
                "location": e.location or "",
                "description": e.description or "",
                "editable": e.user_id == user.id or bool(user.is_admin),
            },
        })

    return out


@app.post("/api/schedules")
def api_schedule_create(
    title: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(""),
    schedule_type: str = Form("COMPANY"),
    memo: str = Form(""),
    color: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not end_date:
        end_date = start_date
    if not color:
        color = SCHEDULE_COLOR_MAP.get(schedule_type, "#6b7280")
    sch = Schedule(
        title=title.strip(),
        start_date=start_date,
        end_date=end_date,
        schedule_type=schedule_type,
        user_id=user.id,
        status="ACTIVE",
        color=color,
        memo=memo.strip(),
    )
    db.add(sch)
    db.commit()
    return RedirectResponse(url="/calendar", status_code=303)


@app.post("/api/schedules/{schedule_id}/delete")
def api_schedule_delete(schedule_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    sch = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not sch:
        raise HTTPException(404, "일정을 찾을 수 없습니다.")
    if sch.user_id != user.id and not bool(user.is_admin):
        raise HTTPException(403, "권한이 없습니다.")
    if sch.document_id:
        raise HTTPException(400, "결재 연동 일정은 직접 삭제할 수 없습니다.")
    sch.status = "CANCELLED"
    db.commit()
    return RedirectResponse(url="/calendar", status_code=303)


# end of generated routes

# 첨부파일 다운로드 라우트
@app.get("/file/attachment/{attachment_id}")
def download_attachment(attachment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    att = db.query(Attachment).get(attachment_id)
    if not att:
        raise HTTPException(404, "첨부파일을 찾을 수 없습니다.")
    doc = db.query(Document).get(att.doc_id)
    if not doc or not can_view_doc(user, doc, db):
        raise HTTPException(403, "권한이 없습니다.")
    if not os.path.isfile(att.filepath):
        raise HTTPException(404, "파일이 존재하지 않습니다.")
    return FileResponse(att.filepath, filename=att.filename, media_type="application/octet-stream")


@app.get("/file/message_attachment/{attachment_id}")
def download_message_attachment(attachment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    att = db.query(MessageAttachment).get(attachment_id)
    if not att:
        raise HTTPException(404, "첨부파일을 찾을 수 없습니다.")
    msg = db.query(Message).get(att.message_id)
    if not msg or not _can_view_message(user, msg):
        raise HTTPException(403, "권한이 없습니다.")
    if not os.path.isfile(att.filepath):
        raise HTTPException(404, "파일이 존재하지 않습니다.")
    return FileResponse(
        att.filepath,
        filename=att.filename,
        media_type=_guess_media_type(att.filepath),
    )


@app.get("/file/trip_registration/{trip_report_id}")
def download_trip_registration(trip_report_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tr = db.query(TripReport).filter(TripReport.id == trip_report_id).first()
    if not tr:
        raise HTTPException(404, "출장복명서를 찾을 수 없습니다.")
    doc = db.query(Document).filter(Document.id == tr.doc_id).first()
    if not doc or not can_view_doc(user, doc, db):
        raise HTTPException(403, "권한이 없습니다.")
    if not tr.registration_file_path or not os.path.isfile(tr.registration_file_path):
        raise HTTPException(404, "사업자등록증 파일이 없습니다.")
    fname = os.path.basename(tr.registration_file_path)
    return FileResponse(tr.registration_file_path, filename=fname, media_type=_guess_media_type(tr.registration_file_path))
