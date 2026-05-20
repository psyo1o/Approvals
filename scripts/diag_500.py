"""Run: python scripts/diag_500.py"""
import json
import traceback
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    out = []
    try:
        from app.main import (
            app, migrate_schema, SessionLocal, Region, User,
            templates, signer, _build_ledger_rows, _parse_ledger_month,
            _parse_accounting_period,
        )
        from fastapi import Request
        from unittest.mock import MagicMock

        migrate_schema()
        out.append("migrate_schema: ok")

        db = SessionLocal()
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            out.append("WARN: no admin user")
        else:
            session = signer.dumps({"uid": admin.id})
            db.close()

            from starlette.testclient import TestClient
            client = TestClient(app)
            client.cookies.set("session", session)

            for path in ["/doc/new", "/accounting/dashboard", "/accounting/ledger"]:
                r = client.get(path)
                out.append(f"{path} -> {r.status_code}")
                if r.status_code >= 500:
                    out.append(r.text[:2000])

        # template tojson
        try:
            templates.env.get_template("doc_new.html").render(
                request=MagicMock(),
                user=MagicMock(is_admin=False),
                regions=[],
            )
            out.append("doc_new template render: ok")
        except Exception as e:
            out.append(f"doc_new template FAIL: {e}")
            out.append(traceback.format_exc())

        db = SessionLocal()
        try:
            rows = _build_ledger_rows(db, "2026-05-01", "2026-05-31")
            out.append(f"ledger rows: {len(rows)}")
        except Exception as e:
            out.append(f"_build_ledger_rows FAIL: {e}")
            out.append(traceback.format_exc())
        db.close()

    except Exception as e:
        out.append(f"FATAL: {e}")
        out.append(traceback.format_exc())

    report = "\n".join(out)
    print(report)
    p = os.path.join(os.path.dirname(__file__), "diag_500_result.txt")
    with open(p, "w", encoding="utf-8") as f:
        f.write(report)

if __name__ == "__main__":
    main()
