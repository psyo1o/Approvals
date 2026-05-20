# 전체 수정 및 기능 추가 이력

> 초기 버그 수정부터 Phase 1~5 확장까지 전체 변경 사항을 기록합니다.

---

## 초기 버그 수정 (시스템 정상화)

### Critical 버그

| # | 문제 | 원인 | 수정 |
|---|------|------|------|
| 1 | Approver 모델 필드명 불일치 | `user_id`/`order`/`status`/`is_active` 사용 | `approver_id`/`order_no`/`action`으로 통일 |
| 2 | `final_doc_no` 미정의 변수 | 품질문서 번호 처리 로직 누락 | 입력값 처리 로직 추가 |
| 3 | `import json` 중복 | 동일 모듈 두 번 선언 | 중복 제거 |
| 4 | `now_dt()` 미정의 함수 | 존재하지 않는 함수 호출 | `now()`로 통일 |
| 5 | `users_json` 참조 오류 | 정의 전 사용 | 해당 라인 삭제 |
| 6 | `import re` 누락 | approver 필드 파싱에 필요 | import 추가 |
| 7 | `grades` 변수 누락 | admin_users()에서 쿼리 없이 전달 | 쿼리 추가 |
| 8 | doc_detail() 중복 쿼리 | users 쿼리 2번 실행 | 중복 제거 |
| 9 | 템플릿 필드명 불일치 | `a.user.username`, `a.status` | `a.approver.name`, `a.action` |
| 10 | 순차 결재 다음 결재자 처리 누락 | 승인 후 다음 순번 변경 안됨 | WAITING → PENDING 전환 로직 추가 |

### 기능 정상화

| 항목 | 설명 |
|------|------|
| 결재자 다중 선택 UI | 최대 5명, 순서 변경(↑↓), 추가/제거 |
| 품질문서 번호 입력 | 직접 입력 + 자동 생성(Q-000001) |
| 상태 한글화 | DRAFT→작성중, WAITING→대기, IN_REVIEW→결재중, APPROVED→완료, REJECTED→반려 |

---

## Phase 1 — DB 모델링 (2026-05-13)

### 추가

| 항목 | 내용 |
|------|------|
| 신규 모델 6개 | Schedule, WorkLog, WorkLogLine, TripReport, TripReportLine, QualityDoc |
| doctype_ko() | WORK_LOG("업무일지"), TRIP_REPORT("출장복명서") 매핑 추가 |
| SCHEDULE_TYPES | 일정 유형 상수 (LEAVE/COMPANY/TEAM_1~5) |
| migrate_schema() | `_ensure_table_exists` + 신규 테이블 컬럼 `_ensure_column` 보강 |

### 수정 파일
- `app/main.py`

---

## Phase 2 — 일정관리 (2026-05-13)

### 추가

| 항목 | 내용 |
|------|------|
| 결재 훅 분리 | `update_doc_status_after_action` → `_on_doc_approved`/`_on_doc_rejected` |
| 휴가→일정 자동 생성 | 승인 시 Schedule 생성, 반려 시 CANCELLED |
| 일정 CRUD API | `GET/POST /api/schedules`, `POST /api/schedules/{id}/delete` |
| 캘린더 UI | FullCalendar 6 CDN, 유형별 색상, 범례 필터, 추가/상세 모달 |
| 모바일 반응형 | 햄버거 메뉴, @media 768/480px, 테이블 가로 스크롤, listMonth 뷰 |

### 수정 파일
- `app/main.py` — 훅 함수, API 라우트
- `app/templates/calendar.html` — 전면 리뉴얼
- `app/templates/base.html` — 반응형 CSS, 햄버거 메뉴

---

## Phase 3 — 업무일지·출장복명서 동적 폼 (2026-05-13)

### 추가

| 항목 | 내용 |
|------|------|
| 문서유형 추가 | doc_new.html에 "업무일지", "출장복명서" 옵션 |
| 동적 폼 | `<template>` 기반 행 추가/삭제 JS 함수 |
| 서버 파싱 | POST /doc/new에서 `form.getlist()`로 다중 행 파싱 |
| 파일 업로드 | 사업자등록증 파일 저장 + 다운로드 라우트 |
| 상세 표시 | doc.html에 업무일지/출장복명서 테이블 렌더링 |

### 수정 파일
- `app/templates/doc_new.html` — 동적 폼 UI
- `app/main.py` POST /doc/new — 데이터 저장 로직
- `app/main.py` doc_view() — 데이터 조회 로직
- `app/templates/doc.html` — 상세 테이블 렌더링

---

## Phase 4 — 품질문서 NAS 연동 (2026-05-13)

### 추가

| 항목 | 내용 |
|------|------|
| NAS 스캔 서비스 | `app/quality_fs.py` — 재귀 트리 스캔, 파일 검색, path traversal 방지 |
| 품질문서 라이브러리 | 사이드바 폴더 트리 + PDF 미리보기 + 재개정 상신 폼 |
| 파일 서빙 | `/quality/file/view` (PDF 인라인), `/quality/file/download` |
| 재개정 상신 | `POST /quality/revise` → Document 생성 → 결재선 이동 |
| 결재 후처리 | `_quality_doc_finalize()` — ACTIVE + SUPERSEDED + 파일 복사 |
| Docker 설정 | NAS 마운트 `/nas_quality:ro` + `QUALITY_NAS_ROOT` 환경변수 |

### 버그 수정

| 문제 | 원인 | 수정 |
|------|------|------|
| 하위 폴더 파일 클릭 시 404 | `scan_tree` 재귀 시 rel_path가 하위 폴더 기준 | `_origin` 파라미터로 원점 유지 |
| PDF 열기 시 500 에러 | 한글 파일명 Content-Disposition Latin-1 인코딩 실패 | RFC 5987 `filename*=UTF-8''` 방식 |

### 신규 파일
- `app/quality_fs.py`
- `app/templates/quality_library.html`

### 수정 파일
- `app/main.py` — 라우트 + 결재 훅
- `docker-compose.yml` — NAS 마운트
- `app/templates/base.html` — 네비 품질문서 링크 추가, 직급 링크 제거

---

## Phase 4-v2 — 이력관리·버전비교 UI (2026-05-14)

### 추가

| 항목 | 내용 |
|------|------|
| QualityDoc 컬럼 | `original_filename`, `archive_path` 추가 |
| 아카이빙 로직 | `{doc_no}_Rev{N}_{YYYYMMDD}.ext` 네이밍으로 `quality_archive/`에 보관 |
| 이력 조회 API | `/api/quality/history?doc_no=...` — 문서별 전 리비전 JSON |
| 검색 API | `/api/quality/search?q=...` — 문서번호/제목 검색 (자동완성) |
| 리비전 PDF | `/quality/revision/pdf?qd_id=...` — 특정 버전 PDF 인라인 |
| 아카이브 다운 | `/quality/archive/download?qd_id=...` — 원본 파일 다운로드 |
| SPA 라이브러리 UI | 좌측 트리 + 우측 PDF 뷰어(iframe) + 이력 테이블 + 검색 드롭다운 + 상신 모달 |

### 수정 파일
- `app/main.py` — QualityDoc 모델, migrate_schema, `_quality_doc_finalize`, 4개 API 라우트
- `app/templates/quality_library.html` — SPA식 전면 개편

## 추가 기능 개선 (2026-05-14) — 알림 고도화

### 추가

| 항목 | 내용 |
|------|------|
| 알림 팝업 UI | `base.html`에 종모양 클릭 시 현재 페이지 내에서 드롭다운되는 알림 팝업 구현 |
| 알림 API 추가 | `/api/notifications/list` (목록), `/api/notifications/read/{id}` (읽음), `/api/notifications/read_all` (전체읽음) |
| 결재 알림 연동 | 상신(결재자), 승인(상신자+다음결재자), 반려(상신자) 시 자동 알림 생성 로직 추가 |
| 쪽지 알림 연동 | 쪽지 발송 시 수신자에게 알림 생성 라우트(`POST /messages/new`) 신설 |
| 공지사항 알림 연동 | 이름에 "공지"가 포함된 게시판에 글 작성 시 전 직원에게 알림 자동 발송 (`POST /board/{id}/new`) |

---

## UI/UX 수정사항

| 날짜 | 내용 |
|------|------|
| 2026-05-13 | `base.html` 네비에서 '직급' 링크 제거 (사용자 관리 페이지 내에서 접근 가능) |
| 2026-05-14 | 품질문서 라이브러리: 버전 비교를 위한 PDF 뷰어 + 이력 테이블 배치 |
| 2026-05-19 | **공통 UI**: `style.css` 통합, Pretendard, 상단 네비 한 줄·아이콘·active 탭, 로그인 카드형 |
| 2026-05-19 | **시스템 관리**: `admin_users` / `admin_grades` / `admin_user_edit` + `partials/admin_nav.html`, CSV 상세 안내 |
| 2026-05-19 | `/admin` → `/admin/users` 리다이렉트, 구독립 `admin.html` 삭제 |

---

## 운영·스키마 수정 (2026-05-19)

| 항목 | 내용 |
|------|------|
| `attachments` 마이그레이션 | `uploader_id`, `filesize`, `created_at` ADD COLUMN + `uploader_id` 백필 |
| 문서 상세 500 | 구 DB에 `uploader_id` 없어 `doc_view` 조회 실패 → 마이그레이션으로 해결 |
| `doc_view` | `selectinload`로 출장/업무일지 lines eager load (완료 문서 보기 안정화) |
| DB 파일명 문서 정정 | 실제 경로 `data/app.db` (README·ARCHITECTURE 반영) |

### 문서 체계 (2026-05-19 상세 반영)

| 문서 | 역할 |
|------|------|
| `README.md` | 설치·메뉴·CSV·회계·migrate·문제 해결 |
| `docs/REFERENCE.md` | **전체 라우트·상태·22 DB 모델·관리 API 갭** |
| `docs/ARCHITECTURE.md` | 흐름도·migrate 12단계·UI 클래스 |
| `docs/DEVELOPMENT_PLAN.md` | Phase 이력·후속 작업(관리 POST) |

---

## Phase 5 — 회계 (2026-05-19)

| 하위 | 내용 |
|------|------|
| 5.1 | `Region`, `Collection` 테이블, `trip_reports.region_id`, `migrate_schema` 시드 |
| 5.2 | 출장 지역 드롭다운·`/api/regions`, `APPROVED_FINAL`, `query_trip_billing_lines()` |
| 5.3 | `/accounting/dashboard` 일월계표 (일·월·**분기**·**연별**) |
| 5.4 | `/accounting/ledger` 미수금대장, `POST /api/collections`, PDF(html2pdf.js) |

**Phase 5.5 없음** — 위 범위로 Phase 5 종료.

### 수정·신규 파일
- `app/main.py`, `doc_new.html`, `doc.html`, `accounting_dashboard.html`, `accounting_ledger.html`, `base.html`

---

## 문서 갱신

| 날짜 | 내용 |
|------|------|
| 2026-05-14 | `README.md` 전면 개편 — 기능 설명, 설치 방법, 사용법, 폴더 구조 |
| 2026-05-14 | `docs/ARCHITECTURE.md` 신규 — 파일 구조, DB 스키마, 라우트 맵, 작동 로직 |
| 2026-05-14 | `docs/DEVELOPMENT_PLAN.md` 갱신 — Phase 4-v2 반영, 전체 정리 |
| 2026-05-14 | `FIXES_SUMMARY.md` 갱신 — 초기 수정 + Phase 1~4 전체 통합 |
| 2026-05-19 | Phase 5 회계 모듈 문서 전반 갱신 |
| 2026-05-19 | UI 개편·시스템 관리·CSV 안내·`attachments` 마이그레이션 문서 반영 |
| 2026-05-19 | **`docs/REFERENCE.md` 신규** — README/ARCHITECTURE/DEVELOPMENT_PLAN 전면 상세 보강 |
| 2026-05-19 | **관리 POST API** — `/admin/users/*`, `/admin/grades/*` 핸들러 추가 |
