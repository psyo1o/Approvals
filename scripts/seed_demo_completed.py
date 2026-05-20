#!/usr/bin/env python3
"""완료함 테스트 문서를 결재란 PDF 예시용으로 갱신."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app")))
os.chdir(os.path.join(os.path.dirname(__file__), "..", "app"))

from main import SessionLocal, seed_demo_completed_pdf_sample  # noqa: E402

if __name__ == "__main__":
    db = SessionLocal()
    try:
        doc_id = seed_demo_completed_pdf_sample(db)
        if doc_id:
            print(f"OK: doc_id={doc_id} → 완료문서에서 PDF 다운로드로 결재란을 확인하세요.")
        else:
            print("FAIL: admin 사용자가 없습니다.")
            sys.exit(1)
    finally:
        db.close()
