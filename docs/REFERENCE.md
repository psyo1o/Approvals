# 상세 참조 — 라우트·스키마·운영

> `app/main.py` 기준 최신 목록입니다. 코드 변경 시 이 문서도 함께 갱신하세요.

---

## 1. 상단 메뉴 (로그인 후)

| 메뉴 | URL | 비고 |
|------|-----|------|
| (브랜드) | `/dashboard` | 영동환경이앤텍 · 전자결재 |
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
| `WORK_LOG` | 업무일지 | WorkLog / WorkLogLine |
| `TRIP_REPORT` | 출장복명서 | TripReport / Line, `APPROVED_FINAL` → 회계 |

### 결재선 (`approvers.action`)

| 값 | 의미 |
|----|------|
| `PENDING` | 결재 대기 (현재 차례) |
| `WAITING` | 순차 모드에서 아직 차례 아님 |
| `APPROVED` | 승인 완료 |
| `REJECTED` | 반려 |

---

## 3. 전체 HTTP 라우트

### 3.1 인증·공통

| 메서드 | URL | 설명 |
|--------|-----|------|
| GET | `/` | → `/dashboard` |
| GET/POST | `/login` | 로그인 |
| GET | `/logout` | 세션 삭제 |
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
| GET | `/completed` | 완료 문서 검색 |
| GET | `/doc/{id}/pdf` | 최종 PDF |
| GET | `/file/original/{id}` | 원본 첨부 |
| GET | `/file/attachment/{id}` | 첨부 다운로드 |
| GET | `/file/trip_registration/{trip_report_id}` | 사업자등록증 |
| GET | `/preview/original/{id}` | 원본 미리보기 |
| GET | `/preview/history/{id}` | 이력 미리보기 |
| GET | `/file/history/{id}` | 이력 파일 |

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
| GET | `/quality/file/view?path=` | NAS PDF 인라인 |
| GET | `/quality/file/download?path=` | NAS 파일 다운로드 |
| POST | `/quality/revise` | 재개정 상신 |
| GET | `/api/quality/history?doc_no=` | 리비전 이력 JSON |
| GET | `/api/quality/search?q=` | 검색 자동완성 |
| GET | `/quality/revision/pdf?qd_id=` | 리비전 PDF |
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
| GET | `/me`, `/my_profile` | 내 정보 |
| GET | `/org` | 조직도 |

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
| GET | `/admin/grades` | 직급 관리 |
| POST | `/admin/grades/add` | 직급 추가 |
| POST | `/admin/grades/{id}/delete` | 직급 비활성화 |
| POST | `/admin/grades/{id}/restore` | 직급 복구 |

---

## 4. DB 모델 전체 (22개)

| 모델 | 테이블 | 용도 |
|------|--------|------|
| Grade | grades | 직급 |
| User | users | 사용자 |
| Document | documents | 결재 문서 |
| Approver | approvers | 결재선 |
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
| Region | regions | 출장/회계 지역 |
| Collection | collections | 수금 |
| TripReport | trip_reports | 출장복명서 헤더 |
| TripReportLine | trip_report_lines | 세금계산서 행 |
| QualityDoc | quality_docs | 품질 리비전 |

### regions / collections

```text
regions: id, name (UNIQUE)
collections: id, company_name, region_name, amount, collection_date, note
```

기본 지역 시드: **원주, 제천, 단양** (`_seed_default_regions`).

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

서버 기동 시 1회 실행 (`startup` 이벤트).

1. `create_all` — 없는 테이블 생성  
2. `documents` — doc_type, rev, leave_*, overtime_*, cert_*, expense_total 등  
3. `users` — must_change_pw, is_admin, grade_id, delegate_id  
4. `grades` — level, is_active  
5. `attachments` — uploader_id, filesize, created_at + uploader_id 백필  
6. `schedules`, `worklogs`, `trip_reports`, `quality_docs` — Phase 1~4 컬럼  
7. `trip_reports.region_id`, `collections.*` — Phase 5  
8. 지역 시드, `APPROVED` → `APPROVED_FINAL` UPDATE  

---

## 6. 환경·볼륨

```yaml
# docker-compose.yml
volumes:
  - ./app:/app          # 소스 (재시작 없이 템플릿/CSS 반영)
  - ./data:/data        # app.db, uploads, final, quality_archive
  - /volume1/품질문서/...:/nas_quality:ro
```

`.env` 예시:

```env
APP_SECRET=랜덤-긴-문자열
APP_ADMIN_ID=admin
APP_ADMIN_PW=강한비밀번호
```

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

FastAPI 0.112, Uvicorn 0.30, SQLAlchemy 2.0, Jinja2, passlib(bcrypt), itsdangerous, python-multipart, reportlab(PDF).
