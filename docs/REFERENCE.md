# 상세 참조 — 라우트·스키마·운영

> `app/main.py` 기준 최신 목록입니다. 코드 변경 시 이 문서도 함께 갱신하세요.

---

## 1. 상단 메뉴 (로그인 후)

| 메뉴 | URL | 비고 |
|------|-----|------|
| (브랜드) | `/dashboard` | 영동환경이앤텍 · 전자결재 |
| (헤더 검색) | `/search` | 통합 검색 입력창 (`q`, `tab`) |
| 검색 | `/search` | Phase 6.2 |
| 문서 | `/dashboard` | `/doc/*` 활성 표시 |
| 완료 | `/completed` | `APPROVED` / `APPROVED_FINAL` |
| 일월계표 | `/accounting/dashboard` | |
| 미수금 | `/accounting/ledger` | |
| 게시판 | `/boards` | |
| 쪽지 | `/messages` | |
| 품질 | `/quality/library` | NAS 라이브러리 |
| 일정 | `/calendar` | FullCalendar |
| 조직도 | `/org` | |
| 내정보 | `/me` | |
| 알림 | (팝업) | `/notifications` 전체 목록 |
| 관리 | `/admin/users` | `is_admin` 만 |
| 나가기 | `/logout` | |

---

## 2. 문서 상태·유형

### 결재 상태 (`documents.status`)

| 코드 | 화면 표시 | 설명 |
|------|-----------|------|
| `DRAFT` | 작성중 | 임시 저장 |
| `IN_REVIEW` / `IN_PROGRESS` | 결재중 | 상신 후 결재 진행 |
| `APPROVED_FINAL` | 완료 | 최종 승인 (회계·완료함 기준) |
| `APPROVED` | 완료 | 레거시; 기동 시 `APPROVED_FINAL` 로 변환 |
| `REJECTED` | 반려 | 재상신 가능 |
| `DELETED` | 삭제 | |

완료 판별: `is_doc_final()` → `APPROVED`, `APPROVED_FINAL`.

### 문서 유형 (`documents.doc_type`)

| 코드 | 한글 | 비고 |
|------|------|------|
| `GENERAL` | 일반 기안 | |
| `LEAVE` | 휴가신청 | 승인 → Schedule |
| `EXPENSE` | 지출결의서 | |
| `OVERTIME` | 연장근무 신청 | |
| `CERTIFICATE` | 증명서 발급 | |
| `QUALITY` | 품질문서 | QualityDoc 연동 |
| `WORK_LOG` | 업무일지 | WorkLog / WorkLogLine, `mode=GRADE_TIER` |
| `TRIP_REPORT` | 출장복명서 | TripReport / Line, `APPROVED_FINAL` → 회계, 관리팀·측정팀 자동 결재 |

### 문서 결재 모드 (`documents.mode`)

| 값 | 설명 |
|----|------|
| `SEQUENTIAL` | 직급 낮은 순 1명씩 (`order_no` 오름차순) |
| `PARALLEL` | 지정 결재자 전원 동시 `PENDING` |
| `GRADE_TIER` | 업무일지: 직급 단계별 순차, **동일 `order_no`는 동시 결재** |

**직급 순서:** `grades.level`(ORM `sort_order`) 작을수록 목록 상단(높은 직급). 상신·자동 결재선은 `level` **큰 값(낮은 직급)부터** `order_no` 부여.

**출장복명서 결재 대상:** `TRIP_REPORT_APPROVAL_DEPTS`(기본 `관리팀,측정팀`). 사용자 `dept`가 접두사와 일치하면 포함.

### 결재선 (`approvers.action`)

| 값 | 의미 |
|----|------|
| `PENDING` | 결재 대기 (현재 차례) |
| `WAITING` | 순차 모드에서 아직 차례 아님 |
| `APPROVED` | 승인 완료 |
| `REJECTED` | 반려 |

### 결재선 확장 (Phase 6.3)

| 컬럼 | 설명 |
|------|------|
| `approver_id` | 실제 결재 담당자 (자동 대결 시 대결자 ID) |
| `original_approver_id` | 자동 대결 전 원 결재자 (NULL이면 위임 없음) |

**자동 대결:** 오늘 `schedules`(LEAVE, ACTIVE)에 해당 사용자가 있고 `users.delegate_id`가 있으면 상신·PENDING 전환 시 `approver_id` 갱신. **delegate_id 없으면 변경 없음.**

### 이벤트 로그 (`event_logs.event`)

| 값 | 설명 |
|----|------|
| `AUTO_DELEGATE` | 부재 자동 대결 (Phase 6.3) |

---

## 3. 전체 HTTP 라우트

### 3.1 인증·공통

| 메서드 | URL | 설명 |
|--------|-----|------|
| GET | `/` | → `/dashboard` |
| GET/POST | `/login` | 로그인 (`?reason=session_expired` 등) |
| GET | `/logout` | 세션 삭제 |

**미들웨어 (Phase 6.1):** `IpAllowlistMiddleware` → `SessionIdleMiddleware` — `/login`, `/static` 제외.
| GET/POST | `/change-password` | 비밀번호 변경 (`must_change_pw`) |

### 3.2 결재·문서

| 메서드 | URL | 설명 |
|--------|-----|------|
| GET | `/dashboard` | 내 문서 + 결재 대기 |
| GET/POST | `/doc/new` | 새 문서 (유형별 동적 폼) |
| GET | `/doc/{id}` | 문서 상세·승인/반려 |
| GET/POST | `/doc/{id}/submit` | 결재선 지정·상신 |
| POST | `/doc/{id}/approve` | 승인 |
| POST | `/doc/{id}/reject` | 반려 |
| POST | `/doc/batch_approve` | 일괄 승인 |
| GET | `/completed` | 완료 문서 검색 (필터) |
| GET | `/search` | **통합 검색** `q`, `tab=all\|document\|post\|attachment` |
| GET | `/doc/{id}/pdf` | 최종 PDF (**워터마크** 적용) |
| GET | `/file/original/{id}` | 원본 첨부 |
| GET | `/file/attachment/{id}` | 첨부 다운로드 |
| GET | `/file/trip_registration/{trip_report_id}` | 사업자등록증 |
| GET | `/preview/original/{id}` | 원본 미리보기 |
| GET | `/preview/history/{id}` | 이력 미리보기 (**워터마크**) |
| GET | `/file/history/{id}` | 이력 파일 (**워터마크**) |

### 3.3 회계

| 메서드 | URL | 설명 |
|--------|-----|------|
| GET | `/accounting/dashboard` | 일월계표 (쿼리: `mode`, `ref`, `year`, `quarter` 등) |
| GET | `/accounting/ledger` | 미수금대장 (`month`, `region_id`, `company`) |
| GET | `/api/regions` | 지역 JSON 목록 |
| POST | `/api/regions` | 지역 등록 `{"name":"..."}` |
| POST | `/api/collections` | 수금 등록 (JSON 또는 form) |

**일월계표 `mode`:** `day` | `month` | `quarter` | `year`  
**청구 집계:** `APPROVED_FINAL` + `TRIP_REPORT` 의 `TripReportLine` (`credit_amount` + `cash_amount`, `line_date` 기준)  
**수금 집계:** `collections` (`collection_date`, `region_name` ↔ `regions.name`)

### 3.4 품질문서

| 메서드 | URL | 설명 |
|--------|-----|------|
| GET | `/quality` | 품질 결재 목록 |
| GET | `/quality/library` | NAS 라이브러리 |
| GET | `/quality/doc/{id}` | 품질 결재 상세 |
| GET | `/quality/file/view?path=` | NAS PDF 인라인 (**PDF만 워터마크**) |
| GET | `/quality/file/download?path=` | NAS 다운로드 (**PDF만 워터마크**) |
| POST | `/quality/revise` | 재개정 상신 |
| GET | `/api/quality/history?doc_no=` | 리비전 이력 JSON |
| GET | `/api/quality/search?q=` | 검색 자동완성 |
| GET | `/quality/revision/pdf?qd_id=` | 리비전 PDF (**워터마크**) |
| GET | `/quality/archive/download?qd_id=` | 아카이브 원본 |

### 3.5 게시판·쪽지·기타

| 메서드 | URL | 설명 |
|--------|-----|------|
| GET | `/boards` | 게시판 목록 |
| GET | `/board/{id}` | 게시글 목록 |
| GET/POST | `/board/{id}/new` | 글 작성 (공지 → 전원 알림) |
| GET | `/post/{id}` | 글 상세 |
| GET | `/messages` | 쪽지함 |
| POST | `/messages/new` | 쪽지 발송 (+ 첨부) |
| GET | `/messages/{id}`, `/message/{id}` | 쪽지 상세 |
| GET | `/file/message_attachment/{id}` | 쪽지 첨부 |
| GET | `/notifications` | 알림 목록 (진입 시 읽음 처리) |
| GET | `/calendar` | 캘린더 |
| GET/POST | `/me` | 내 정보 (부서·직급 드롭다운, `POST` 저장) |
| GET | `/my_profile` | (레거시) 내 정보 |
| GET | `/org` | 조직도 (부서별 카드) |

### 3.6 알림·일정 API

| 메서드 | URL | 설명 |
|--------|-----|------|
| GET | `/api/notifications/count` | 미읽음 수 (30초 폴링) |
| GET | `/api/notifications/list` | 팝업용 최근 30건 |
| POST | `/api/notifications/read/{id}` | 읽음 + 링크 이동용 |
| POST | `/api/notifications/read_all` | 전체 읽음 |
| GET | `/api/schedules` | FullCalendar 이벤트 JSON |
| POST | `/api/schedules` | 일정 생성 |
| POST | `/api/schedules/{id}/delete` | 일정 취소 |
| GET/POST | `/api/events` | 레거시 CalendarEvent |
| POST | `/api/events/{id}/delete` | 레거시 삭제 |

### 3.7 관리자 (`require_admin`)

| 메서드 | URL | 설명 |
|--------|-----|------|
| GET | `/admin` | → `/admin/users` |
| GET | `/admin/users` | 사용자 관리 |
| POST | `/admin/users/add` | 사용자 추가 (form) |
| POST | `/admin/users/import_csv` | CSV 업로드 |
| POST | `/admin/users/reset_pw` | PW 초기화 (`user_id`) |
| POST | `/admin/users/{id}/delete` | 비활성화 |
| GET | `/admin/users/{id}/edit` | 수정 폼 |
| POST | `/admin/users/{id}/edit` | 수정 저장 |
| GET | `/admin/depts` | 부서 관리 |
| POST | `/admin/depts/add` | 부서 추가 |
| POST | `/admin/depts/{id}/move-up`, `move-down` | 부서 표시 순서 |
| POST | `/admin/depts/{id}/delete`, `restore` | 부서 비활성화·복구 |
| GET | `/admin/grades` | 직급 관리 |
| POST | `/admin/grades/add` | 직급 추가 |
| POST | `/admin/grades/{id}/move-up`, `move-down` | 직급 결재 순서 |
| POST | `/admin/grades/{id}/delete` | 직급 비활성화 |
| POST | `/admin/grades/{id}/restore` | 직급 복구 |

**사용자·내정보:** `dept_id`, `grade_id` 폼만 반영. 수기 `dept`/`grade` 텍스트 필드 없음.

---

## 4. DB 모델 전체

| 모델 | 테이블 | 용도 |
|------|--------|------|
| Grade | grades | 직급 (`level`=순서, 작을수록 높은 직급) |
| Department | departments | 부서 (`sort_order`) |
| User | users | 사용자 |
| Document | documents | 결재 문서 |
| Approver | approvers | 결재선 (`original_approver_id` Phase 6.3) |
| ExpenseItem | expense_items | 지출 항목 |
| EventLog | event_logs | 이벤트 로그 |
| Board | boards | 게시판 |
| Post | posts | 게시글 |
| Message | messages | 쪽지 |
| MessageAttachment | message_attachments | 쪽지 첨부 |
| Attachment | attachments | 문서 첨부 |
| CalendarEvent | calendar_events | 레거시 일정 |
| Notification | notifications | 알림 |
| Schedule | schedules | 일정 (휴가 연동) |
| WorkLog | worklogs | 업무일지 |
| WorkLogLine | worklog_lines | 업무일지 행 |
| Branch | branches | 지사 (원주 WJ, 제천 JC) |
| Region | regions | 출장/회계 지역 (**지사별**, `branch_id`+`name` UNIQUE) |
| Collection | collections | 수금 (`branch_id`) |
| TripReport | trip_reports | 출장복명서 헤더 |
| TripReportLine | trip_report_lines | 세금계산서 행 |
| QualityDoc | quality_docs | 품질 리비전 |

### branches / regions / collections (Phase 7)

```text
branches: id, name, code, is_headquarters
regions: id, name, branch_id  — UNIQUE(branch_id, name)
collections: id, company_name, region_name, amount, collection_date, note, branch_id
documents.branch_id — 출장복명서 회계 청구 집계 기준
```

기본 지역 시드: **원주, 제천, 단양** — 지사 1·2 각각 (`_seed_regions_per_branch`).

**회계 조회:** 일반 사용자 = `users.branch_id`. 관리자·`can_switch_branch_view` = `?branch_id=` 또는 헤더 `view_branch_id` 쿠키.

**결재 문서 등록:** 상신 시 `documents.branch_id` = 작성자 `users.branch_id` (WORK_LOG, TRIP_REPORT, LEAVE, GENERAL 등 전 유형).

**결재 가시성** (`branch_scope.visible_document_ids`):

| 조건 | 포함 |
|------|------|
| 조회 지사 | `documents.branch_id == resolve_view_branch_id()` (기본 소속 지사) |
| 결재 참여 | `approvers`에 본인(또는 대결 위임자)이 있는 **타지사** 문서 |
| 본인 작성 | `creator_id` 본인 문서(지사 무관) |

**조회 지사 전환:** `is_admin` 또는 **원주본사**(`is_headquarters`) + 「대표」 이상. 제천 대표 불가. **통합 목록 없음.**

**업무일지:** 전 직원(제외 직급·휴가 제외), 결재 없이 `RECORD` 즉시 완료.

**출장복명서 작성:** `doc_requirements` — 부서 접두사 기본 `관리,측정`.

### trip_report_lines (회계 청구)

| 컬럼 | 설명 |
|------|------|
| line_date | 집계 기준일 |
| company_name | 업체명 (미수금 키) |
| credit_amount | 외상 |
| cash_amount | 현금 |
| volume_no, doc_number, details | 세부 |

---

## 5. migrate_schema() 요약

서버 기동 시 1회 실행 (`app/database.py` → `run_schema_migration`, `startup`).

1. `create_all` — 없는 테이블 생성  
2. `documents` — doc_type, rev, leave_*, overtime_*, cert_*, expense_total 등  
3. `users` — must_change_pw, is_admin, grade_id, delegate_id  
4. `approvers` — **original_approver_id** (Phase 6.3)  
5. `grades` — level, is_active  
6. `attachments` — uploader_id, filesize, created_at + uploader_id 백필  
7. `schedules`, `worklogs`, `trip_reports`, `quality_docs` — Phase 1~4 컬럼  
8. `trip_reports.region_id`, `collections.*` — Phase 5  
9. **Phase 7** — `branches`, `users/documents/quality_docs/collections/regions.branch_id`, regions 테이블 재구성( SQLite )  
10. 지역 시드(지사별), `APPROVED` → `APPROVED_FINAL` UPDATE  

**Dialect:** SQLite `PRAGMA` / PostgreSQL·MariaDB `inspect` — `DATABASE_URL` 미설정 시 `sqlite:///{APP_DATA_DIR}/app.db`.

---

## 6. 환경·볼륨

```yaml
# docker-compose.yml
volumes:
  - ./app:/app          # 소스 (재시작 없이 템플릿/CSS 반영)
  - ./data:/data        # app.db, uploads, final, quality_archive
  - /volume1/품질문서/...:/nas_quality:ro
```

`.env` 예시 (전체는 프로젝트 루트 `.env.example`):

```env
APP_SECRET=랜덤-긴-문자열
APP_ADMIN_ID=admin
APP_ADMIN_PW=강한비밀번호
APP_DATA_DIR=/data
# DATABASE_URL=postgresql+psycopg://user:pass@host:5432/approval
SESSION_IDLE_SECONDS=7200
SESSION_ABSOLUTE_SECONDS=2592000
# ALLOWED_IPS=127.0.0.1,192.168.10.*
# TRUST_PROXY=1
```

### Phase 6 모듈 (`app/`)

| 파일 | 역할 |
|------|------|
| `database.py` | 엔진·URL·마이그레이션 |
| `security.py` | 세션 유휴·IP 미들웨어 |
| `search.py` | 통합 검색 |
| `delegation.py` | 부재 자동 대결 |
| `pdf_watermark.py` | PDF 워터마크 합성 |
| `main.py` | FastAPI 앱·모델·라우트 (기존 단일 파일 구조 유지) |

---

## 7. 유틸 스크립트 (`scripts/`)

| 스크립트 | 용도 |
|----------|------|
| `check_db.py` | DB·admin 사용자 확인 |
| `check_completed.py` | 완료 문서 HTTP 점검 |
| `test_pages.py` / `test_endpoints.py` | 페이지·API 스모크 테스트 |
| `diag_500.py` | 500 원인 진단 |

---

## 8. Python 패키지 (`requirements.txt`)

FastAPI 0.112, Uvicorn 0.30, SQLAlchemy 2.0, Jinja2, passlib, itsdangerous, python-multipart, reportlab, pypdf, xhtml2pdf, **python-dotenv**, **psycopg[binary]**, **pymysql**.
