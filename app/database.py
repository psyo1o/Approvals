"""DB 연결 추상화 및 dialect-aware 스키마 마이그레이션 (Phase 6.1)."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional, Set, Type

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql.schema import MetaData

# 프로젝트 루트 .env (로컬) + 컨테이너 cwd
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
load_dotenv()

DEFAULT_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
DATA_DIR = os.getenv("APP_DATA_DIR", DEFAULT_DATA_DIR)
DB_PATH = os.path.join(DATA_DIR, "app.db")

os.makedirs(DATA_DIR, exist_ok=True)

Base = declarative_base()


def resolve_database_url() -> str:
    explicit = (os.getenv("DATABASE_URL") or "").strip()
    if explicit:
        return explicit
    return f"sqlite:///{DB_PATH}"


def create_db_engine(url: str) -> Engine:
    connect_args: dict[str, Any] = {}
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    else:
        kwargs["pool_size"] = int(os.getenv("DB_POOL_SIZE", "5"))
        kwargs["max_overflow"] = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    return create_engine(url, connect_args=connect_args, **kwargs)


DATABASE_URL = resolve_database_url()
engine = create_db_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _is_sqlite(eng: Engine) -> bool:
    return eng.dialect.name == "sqlite"


def _table_columns(conn: Connection, eng: Engine, table: str) -> Set[str]:
    if _is_sqlite(eng):
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {str(r[1]) for r in rows}
    return {c["name"] for c in inspect(eng).get_columns(table)}


def _ensure_table_exists(conn: Connection, eng: Engine, table: str) -> bool:
    if _is_sqlite(eng):
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
            {"t": table},
        ).fetchall()
        return len(rows) > 0
    return table in inspect(eng).get_table_names()


def _sqlite_ddl_to_generic(ddl: str) -> str:
    """SQLite 전용 DEFAULT 등을 PostgreSQL/MariaDB 호환 DDL로 단순 변환."""
    s = ddl
    s = re.sub(r"DEFAULT\s*\(\s*datetime\s*\(\s*'now'\s*\)\s*\)", "", s, flags=re.IGNORECASE)
    return s.strip()


def _ensure_column(
    conn: Connection,
    eng: Engine,
    table: str,
    col: str,
    ddl_sqlite: str,
    ddl_other: Optional[str] = None,
) -> None:
    cols = _table_columns(conn, eng, table)
    if col in cols:
        return
    ddl = ddl_sqlite if _is_sqlite(eng) else (ddl_other if ddl_other is not None else _sqlite_ddl_to_generic(ddl_sqlite))
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
    print(f"[migrate] added column {table}.{col} ({ddl})")


_DEFAULT_REGION_NAMES = ("원주", "제천", "단양")


def _seed_default_regions(conn: Connection, eng: Engine) -> None:
    """레거시: branch_id 없는 구 DB만 1회 시드."""
    if not _ensure_table_exists(conn, eng, "regions"):
        return
    cols = _table_columns(conn, eng, "regions")
    if "branch_id" in cols:
        return
    count = conn.execute(text("SELECT COUNT(*) FROM regions")).scalar() or 0
    if count > 0:
        return
    for name in _DEFAULT_REGION_NAMES:
        conn.execute(text("INSERT INTO regions (name) VALUES (:name)"), {"name": name})
    print(f"[migrate] seeded {len(_DEFAULT_REGION_NAMES)} default regions")


def _migrate_regions_multibranch(conn: Connection, eng: Engine) -> None:
    """regions.name 전역 UNIQUE → (branch_id, name) 복합 UNIQUE."""
    if not _ensure_table_exists(conn, eng, "regions"):
        return
    cols = _table_columns(conn, eng, "regions")
    if "branch_id" in cols:
        _seed_regions_per_branch(conn, eng)
        return
    if _is_sqlite(eng):
        conn.execute(
            text(
                "CREATE TABLE regions_new ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "name VARCHAR(50) NOT NULL, "
                "branch_id INTEGER NOT NULL DEFAULT 1, "
                "UNIQUE (branch_id, name))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO regions_new (id, name, branch_id) "
                "SELECT id, name, 1 FROM regions"
            )
        )
        conn.execute(text("DROP TABLE regions"))
        conn.execute(text("ALTER TABLE regions_new RENAME TO regions"))
        print("[migrate] regions table rebuilt with branch_id")
    else:
        _ensure_column(conn, eng, "regions", "branch_id", "INTEGER NOT NULL DEFAULT 1")
        conn.execute(text("UPDATE regions SET branch_id = 1 WHERE branch_id IS NULL"))
    _seed_regions_per_branch(conn, eng)


def _seed_regions_per_branch(conn: Connection, eng: Engine) -> None:
    if not _ensure_table_exists(conn, eng, "regions"):
        return
    if "branch_id" not in _table_columns(conn, eng, "regions"):
        return
    added = 0
    for bid in (1, 2):
        for name in _DEFAULT_REGION_NAMES:
            row = conn.execute(
                text(
                    "SELECT 1 FROM regions WHERE name = :n AND branch_id = :b LIMIT 1"
                ),
                {"n": name, "b": bid},
            ).fetchone()
            if row:
                continue
            conn.execute(
                text("INSERT INTO regions (name, branch_id) VALUES (:n, :b)"),
                {"n": name, "b": bid},
            )
            added += 1
    if added:
        print(f"[migrate] seeded {added} region rows (per branch)")


def run_schema_migration(model_base: Type[Any]) -> None:
    """모델이 등록된 Base 서브클래스 기준으로 create_all + ADD COLUMN 보강."""
    metadata: MetaData = model_base.metadata
    try:
        with engine.begin() as conn:
            metadata.create_all(bind=engine)

            ec = lambda t, c, d, o=None: _ensure_column(conn, engine, t, c, d, o)  # noqa: E731

            ec("documents", "doc_type", "TEXT DEFAULT 'GENERAL'")
            ec("documents", "doc_no", "TEXT DEFAULT ''")
            ec("documents", "rev", "INTEGER DEFAULT 1")
            ec("documents", "base_doc_id", "INTEGER")
            ec("documents", "status", "TEXT DEFAULT 'DRAFT'")
            ec("documents", "is_deleted", "INTEGER DEFAULT 0")
            ec("documents", "mode", "TEXT DEFAULT 'SEQUENTIAL'")
            ec("documents", "created_at", "TEXT DEFAULT (datetime('now'))", "TIMESTAMP")
            ec("documents", "updated_at", "TEXT DEFAULT (datetime('now'))", "TIMESTAMP")
            ec("documents", "leave_start", "TEXT DEFAULT ''")
            ec("documents", "leave_end", "TEXT DEFAULT ''")
            ec("documents", "leave_kind", "TEXT DEFAULT ''")
            ec("documents", "leave_hours", "TEXT DEFAULT ''")
            ec("documents", "expense_total", "INTEGER DEFAULT 0")
            ec("documents", "overtime_date", "TEXT DEFAULT ''")
            ec("documents", "overtime_start", "TEXT DEFAULT ''")
            ec("documents", "overtime_end", "TEXT DEFAULT ''")
            ec("documents", "overtime_reason", "TEXT DEFAULT ''")
            ec("documents", "work_hours", "TEXT DEFAULT ''")
            ec("documents", "cert_type", "TEXT DEFAULT ''")
            ec("documents", "cert_usage", "TEXT DEFAULT ''")

            ec("users", "must_change_pw", "INTEGER DEFAULT 0")
            ec("users", "is_admin", "INTEGER DEFAULT 0")
            ec("users", "grade_id", "INTEGER")
            ec("users", "delegate_id", "INTEGER")

            if _ensure_table_exists(conn, engine, "approvers"):
                ec("approvers", "original_approver_id", "INTEGER")

            ec("grades", "level", "INTEGER DEFAULT 1")
            ec("grades", "is_active", "INTEGER DEFAULT 1")

            if not _ensure_table_exists(conn, engine, "departments"):
                conn.execute(
                    text(
                        "CREATE TABLE departments ("
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "name VARCHAR(120) NOT NULL UNIQUE, "
                        "sort_order INTEGER NOT NULL DEFAULT 1, "
                        "is_active INTEGER DEFAULT 1)"
                    )
                )
                print("[migrate] created departments table")
            else:
                ec("departments", "sort_order", "INTEGER DEFAULT 1")
                ec("departments", "is_active", "INTEGER DEFAULT 1")

            if _ensure_table_exists(conn, engine, "attachments"):
                ec("attachments", "uploader_id", "INTEGER")
                ec("attachments", "filesize", "INTEGER DEFAULT 0")
                ec("attachments", "created_at", "TEXT DEFAULT (datetime('now'))", "TIMESTAMP")
                conn.execute(
                    text(
                        "UPDATE attachments SET uploader_id = ("
                        "  SELECT creator_id FROM documents WHERE documents.id = attachments.doc_id"
                        ") WHERE uploader_id IS NULL"
                    )
                )

            if _ensure_table_exists(conn, engine, "schedules"):
                ec("schedules", "color", "TEXT DEFAULT ''")
                ec("schedules", "memo", "TEXT DEFAULT ''")
                ec("schedules", "document_id", "INTEGER")
                ec("schedules", "schedule_type", "TEXT NOT NULL DEFAULT 'COMPANY'")
                ec("schedules", "status", "TEXT NOT NULL DEFAULT 'ACTIVE'")
                if "schedule_type" in _table_columns(conn, engine, "schedules"):
                    conn.execute(
                        text(
                            "UPDATE schedules SET schedule_type = 'LEAVE' "
                            "WHERE document_id IS NOT NULL AND schedule_type = 'COMPANY' "
                            "AND document_id IN ("
                            "  SELECT id FROM documents WHERE doc_type = 'LEAVE'"
                            ")"
                        )
                    )

            if _ensure_table_exists(conn, engine, "worklogs"):
                ec("worklogs", "work_date", "TEXT DEFAULT ''")

            if _ensure_table_exists(conn, engine, "trip_reports"):
                ec("trip_reports", "destination", "TEXT DEFAULT ''")
                ec("trip_reports", "purpose", "TEXT DEFAULT ''")
                ec("trip_reports", "registration_file_path", "TEXT")

            if _ensure_table_exists(conn, engine, "quality_docs"):
                ec("quality_docs", "status", "TEXT DEFAULT 'ACTIVE'")
                ec("quality_docs", "uploader_id", "INTEGER")
                ec("quality_docs", "original_filename", "TEXT DEFAULT ''")
                ec("quality_docs", "archive_path", "TEXT DEFAULT ''")

            if _ensure_table_exists(conn, engine, "trip_reports"):
                ec("trip_reports", "region_id", "INTEGER")

            if _ensure_table_exists(conn, engine, "collections"):
                ec("collections", "company_name", "TEXT DEFAULT ''")
                ec("collections", "region_name", "TEXT DEFAULT ''")
                ec("collections", "amount", "INTEGER DEFAULT 0")
                ec("collections", "collection_date", "TEXT DEFAULT ''")
                ec("collections", "note", "TEXT DEFAULT ''")
                ec("collections", "branch_id", "INTEGER DEFAULT 1")
                conn.execute(
                    text("UPDATE collections SET branch_id = 1 WHERE branch_id IS NULL")
                )

            _seed_default_regions(conn, engine)

            # Phase 7 — 지사(Branch)
            if not _ensure_table_exists(conn, engine, "branches"):
                conn.execute(
                    text(
                        "CREATE TABLE branches ("
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "name VARCHAR(120) NOT NULL, "
                        "code VARCHAR(20) NOT NULL UNIQUE, "
                        "is_headquarters INTEGER DEFAULT 0)"
                    )
                )
                print("[migrate] created branches table")
            for bid, bname, bcode, hq in (
                (1, "원주본사", "WJ", 1),
                (2, "제천지사", "JC", 0),
            ):
                conn.execute(
                    text(
                        "INSERT OR IGNORE INTO branches (id, name, code, is_headquarters) "
                        "VALUES (:id, :name, :code, :hq)"
                    ),
                    {"id": bid, "name": bname, "code": bcode, "hq": hq},
                )

            ec("users", "branch_id", "INTEGER DEFAULT 1")
            ec("documents", "branch_id", "INTEGER DEFAULT 1")
            if _ensure_table_exists(conn, engine, "quality_docs"):
                ec("quality_docs", "branch_id", "INTEGER DEFAULT 1")

            if _ensure_table_exists(conn, engine, "users"):
                conn.execute(text("UPDATE users SET branch_id = 1 WHERE branch_id IS NULL"))
            if _ensure_table_exists(conn, engine, "documents"):
                conn.execute(text("UPDATE documents SET branch_id = 1 WHERE branch_id IS NULL"))
            if _ensure_table_exists(conn, engine, "quality_docs"):
                conn.execute(text("UPDATE quality_docs SET branch_id = 1 WHERE branch_id IS NULL"))

            if not _ensure_table_exists(conn, engine, "work_schedule_entries"):
                conn.execute(
                    text(
                        "CREATE TABLE work_schedule_entries ("
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "user_id INTEGER NOT NULL, "
                        "branch_id INTEGER NOT NULL DEFAULT 1, "
                        "work_date TEXT NOT NULL, "
                        "early_hours REAL NOT NULL DEFAULT 0, "
                        "overtime_hours REAL NOT NULL DEFAULT 0, "
                        "weekend_hours REAL NOT NULL DEFAULT 0, "
                        "note TEXT DEFAULT '', "
                        "is_day_off INTEGER DEFAULT 0, "
                        "off_reason TEXT DEFAULT '', "
                        "source_doc_id INTEGER, "
                        "updated_at TEXT DEFAULT (datetime('now')), "
                        "UNIQUE(user_id, work_date))"
                    )
                )
                print("[migrate] created work_schedule_entries table")
            elif _ensure_table_exists(conn, engine, "work_schedule_entries"):
                ec("work_schedule_entries", "is_day_off", "INTEGER DEFAULT 0")
                ec("work_schedule_entries", "off_reason", "TEXT DEFAULT ''")

            if not _ensure_table_exists(conn, engine, "work_timesheet_months"):
                conn.execute(
                    text(
                        "CREATE TABLE work_timesheet_months ("
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "user_id INTEGER NOT NULL, "
                        "branch_id INTEGER NOT NULL DEFAULT 1, "
                        "year_month TEXT NOT NULL, "
                        "status TEXT NOT NULL DEFAULT 'DRAFT', "
                        "doc_id INTEGER, "
                        "updated_at TEXT DEFAULT (datetime('now')), "
                        "UNIQUE(user_id, year_month))"
                    )
                )
                print("[migrate] created work_timesheet_months table")

            _migrate_regions_multibranch(conn, engine)

            if not _ensure_table_exists(conn, engine, "schedule_trip_members"):
                conn.execute(
                    text(
                        "CREATE TABLE schedule_trip_members ("
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "schedule_id INTEGER NOT NULL, "
                        "user_id INTEGER NOT NULL, "
                        "UNIQUE (schedule_id, user_id))"
                    )
                )
                print("[migrate] created schedule_trip_members table")

            conn.execute(
                text("UPDATE documents SET status = 'APPROVED_FINAL' WHERE status = 'APPROVED'")
            )

            print(f"[migrate] schema migration completed ({engine.dialect.name})")
    except Exception as e:
        print(f"[migrate] migrate_schema failed: {e}")
