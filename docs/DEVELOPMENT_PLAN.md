# 결재 시스템 확장 — 개발 계획 및 진행 기록

> 일정관리 / 업무일지·출장복명서 / 품질문서(NAS 연동) / **회계(일월계표·미수금)** / **인프라·보안·통합검색·대결·PDF** 확장을 **Phase 1~6**으로 나누어 구현.  
> 각 Phase 완료 시 이 문서에 기록 갱신.

---

## 진행 요약

| Phase | 제목 | 상태 | 완료일 |
|-------|------|------|--------|
| 1 | DB 모델링 및 스키마 | ✅ 완료 | 2026-05-13 |
| 2 | 일정관리 UI·API·결재 훅 | ✅ 완료 | 2026-05-13 |
| 3 | 업무일지·출장복명서 동적 폼 | ✅ 완료 | 2026-05-13 |
| 4 | 품질문서 NAS 연동·재개정 | ✅ 완료 | 2026-05-13 |
| 4-v2 | 품질문서 이력관리·버전비교 UI | ✅ 완료 | 2026-05-14 |
| 기타 | 알림 고도화 및 공지사항 연동 | ✅ 완료 | 2026-05-14 |
| **5** | **회계 — 지역·수금·일월계표·미수금대장** | ✅ 완료 | 2026-05-19 |
| 5+ | 일월계표 분기·연별 조회 (5.3 확장) | ✅ 완료 | 2026-05-19 |
| UI | 공통·관리 화면 디자인 개편 | ✅ 완료 | 2026-05-19 |
| **6.1** | **DB 추상화·세션/IP 보안** | ✅ 완료 | 2026-05-20 |
| **6.2** | **글로벌 통합 검색** | ✅ 완료 | 2026-05-20 |
| **6.3** | **부재중 자동 대결** | ✅ 완료 | 2026-05-20 |
| **6.4** | **PDF 동적 워터마크** | ✅ 완료 | 2026-05-20 |
| **7** | **멀티 지사 (원주·제천)** | ✅ 완료 | 2026-05-21 |

> **Phase 5.5는 계획에 없음.** 5.1~5.4 + 분기·연별 확장으로 Phase 5 범위 종료.

---

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-05-13 | 문서 최초 작성. Phase 1~4 브리핑 반영 |
| 2026-05-13 | **Phase 1 완료**: 신규 모델 6개 추가, `migrate_schema()` 보강 |
| 2026-05-13 | **Phase 2 완료**: FullCalendar 6 연동, 결재 훅, 모바일 반응형 |
| 2026-05-13 | **Phase 3 완료**: 업무일지/출장복명서 동적 폼, 파일 업로드 |
| 2026-05-13 | **Phase 4 완료**: NAS 스캔, 품질문서 라이브러리, 재개정 상신 |
| 2026-05-13 | 버그 수정: `scan_tree` rel_path 재귀 버그, 한글 파일명 인코딩 |
| 2026-05-14 | **알림 센터 고도화**: (1) `base.html` 알림 아이콘을 인페이지 드롭다운 팝업으로 변경. (2) `api_notifications_list`, `api_notification_read` 등 알림 API 추가. (3) 결재 상신, 승인, 반려, 쪽지 발송 시 `_notify` 헬퍼로 알림 자동 생성 로직 추가. (4) "공지"가 포함된 게시판에 글 작성 시 전 직원에게 알림 발송되도록 구현. |
| 2026-05-14 | **Phase 4-v2 완료**: 이력관리·버전비교 UI, 아카이빙, API 추가 |
| 2026-05-19 | **Phase 5 완료**: Region/Collection, 출장 지역 UI, 일월계표, 미수금대장, `APPROVED_FINAL` |
| 2026-05-19 | 일월계표 **분기·연별** 조회 추가 (5.3 확장, 별도 Phase 번호 없음) |
| 2026-05-19 | **UI 개편**: `style.css` 통합, 상단 네비 한 줄·아이콘, Pretendard, 관리 화면(사용자/직급 탭·CSV 안내) |
| 2026-05-19 | **스키마 보강**: `attachments.uploader_id` 등 구 DB 마이그레이션, 문서 상세 500 오류 수정 |
| 2026-05-19 | `/admin` → `/admin/users` 리다이렉트, 구 `admin.html` 제거 |
| 2026-05-19 | **`docs/REFERENCE.md` 신규** — 전 라우트·상태·DB·관리 API 현황 상세 목록 |
| 2026-05-19 | **관리 POST API 구현** — 사용자·CSV·직급 CRUD, PW 초기화, flash 메시지 |
| 2026-05-20 | **Phase 6 완료** — DB 다중 dialect, 세션/IP, `/search`, 자동 대결, PDF 워터마크 |
| 2026-05-21 | **직급·부서·결재선 확장**: `departments` 마스터, `/admin/depts`, 사용자·`/me` 드롭다운만(수기 입력 제거) |
| 2026-05-21 | **직급 순서(▲▼)**: `grades.level` 기반 결재 순서, 상신 시 자동 정렬, `GRADE_TIER`(업무일지 동직급 병렬) |
| 2026-05-21 | **출장복명서**: `TRIP_REPORT_APPROVAL_DEPTS` — 관리팀·측정팀 자동 결재선 |
| 2026-05-21 | **UI**: 상단 메뉴 조직도 노출 개선(햄버거·줄바꿈), 직급 순서 중복값 정규화 |
| 2026-05-21 | **Phase 7 완료**: `branches`, `branch_scope.py`, 문서·품질·회계·조직도 지사 격리, 게시판 통합, NAS 2볼륨 |

---

## Phase 7 — 멀티 지사 (원주본사 WJ · 제천지사 JC)

**목표:** 논리적 데이터 격리 — 결재 문서는 지사별 저장·조회, 대표 이상·관리자는 지사 전환 조회, 결재 참여 시 타지사 문서 열람, 게시판·조직도는 통합.

### DB

| 테이블/컬럼 | 내용 |
|-------------|------|
| `branches` | id, name, code, is_headquarters |
| `users.branch_id`, `documents.branch_id`, `quality_docs.branch_id` | 기본 1 백필 |
| `collections.branch_id` | 수금 지사 |
| `regions.branch_id` | 지역 마스터 지사별 (`UNIQUE(branch_id, name)`) |

### 결재 문서 — 등록·조회 (업무일지·출장복명서 포함)

| 항목 | 규칙 |
|------|------|
| **등록** | 상신 시 `documents.branch_id` = `users.branch_id` (WORK_LOG, TRIP_REPORT, LEAVE, GENERAL 등 **전 doc_type 동일**) |
| **문서번호** | `{유형}-{지사코드}-{YYMM}-{순번}` (`allocate_doc_no`) |
| **목록·대시보드·검색(문서)** | `resolve_view_branch_id` — 쿠키/쿼리 `view_branch_id`, 없으면 소속 지사. **원주+제천 통합 목록 없음** |
| **가시 범위** | `visible_document_ids`: (1) **조회 지사** 문서 (2) 본인 결재선·대결 위임 타지사 문서 (3) 본인 작성 문서 |
| **조회 지사 전환** | `is_admin` **또는** 원주본사(`is_headquarters`) 소속 + 「대표」 이상. **제천 대표 제외**, `POST /branch-view` |
| **업무일지** | 저장 시 `APPROVED_FINAL` / `RECORD` — **결재선 없음** |
| **출장복명서 작성** | 부서 접두사 기본 `관리,측정` (관리팀·측정팀 포함) |
| **레거시** | `is_global_view` — 관리자 전 지사 자동 노출 **미사용** |

### 작성 대상 (지사와 무관, `app/doc_requirements.py`)

| 유형 | 규칙 |
|------|------|
| 업무일지 | 활성 직원 전원, `WORK_LOG_EXEMPT_GRADES`(기본 관리자 직급)·당일 휴가 제외 |
| 출장복명서 | `TRIP_REPORT_WRITER_DEPTS` (기본 관리팀·측정팀), `is_admin`만으로는 불가 |

### 모듈·규칙

| 파일 | 역할 |
|------|------|
| `app/branch_scope.py` | 가시 문서 ID, 결재 후보, 문서번호, 검색 visible clause, 조회 지사 |
| `app/doc_requirements.py` | 업무일지·출장복명서 작성/의무 판단 |
| `app/quality_fs.py` | `nas_root_for_branch()` |
| `CROSS_BRANCH_REP_GRADE_NAME` | 기본 `대표` — sort_order 이하(숫자 작을수록 높음) = 전 지사 결재 후보·조회 전환 |

### 화면·API

- 헤더 **조회** 드롭다운(전환 권한자), 지사 배지, 사용자 관리·CSV `branch` 컬럼
- `/api/regions` · 출장 지역: **소속·조회 지사**만
- 회계: 청구=`Document.branch_id`, 수금=`Collection.branch_id`; 전환 권한자 `?branch_id=` 또는 헤더와 동일 쿠키

### 통합(지사 무관)

- 게시판, 조직도(지사별 섹션), 일정 캘린더(전체 일정 API)

### docker-compose

- `QUALITY_NAS_ROOT_WONJU`, `QUALITY_NAS_ROOT_JECHEON` 볼륨 분리

---

## Phase 1 — DB 모델링 및 스키마

**목표:** 확장 기능에 필요한 신규 DB 테이블 정의 + 안전한 마이그레이션

### 추가된 모델 (6개)

| 모델 | 테이블 | 용도 |
|------|--------|------|
| Schedule | schedules | 일정 (휴가/전체/팀별) |
| WorkLog | worklogs | 업무일지 헤더 |
| WorkLogLine | worklog_lines | 업무일지 행 |
| TripReport | trip_reports | 출장복명서 헤더 |
| TripReportLine | trip_report_lines | 출장복명서 세금계산서 행 |
| QualityDoc | quality_docs | 품질문서 리비전 이력 |

### 수정된 파일

| 파일 | 변경 |
|------|------|
| `app/main.py` L312~L408 | 6개 모델 클래스 추가 |
| `app/main.py` migrate_schema() | `create_all` + `_ensure_column` 보강 |
| `app/main.py` doctype_ko() | WORK_LOG, TRIP_REPORT 매핑 추가 |
| `app/main.py` | SCHEDULE_TYPES 상수 + schedule_type_ko() 헬퍼 |

---

## Phase 2 — 일정관리 (Calendar) UI 및 API

**목표:** FullCalendar 캘린더, 결재 승인 시 자동 일정 생성, 모바일 대응

### 핵심 동작
- 휴가 결재 승인 → `_on_doc_approved()` → Schedule 자동 생성
- 휴가 반려 → `_on_doc_rejected()` → Schedule CANCELLED
- `/api/schedules` GET → FullCalendar JSON (Schedule + CalendarEvent 통합)

### 수정된 파일

| 파일 | 변경 |
|------|------|
| `app/templates/calendar.html` | 전면 리뉴얼: FullCalendar 6 CDN, 범례 필터, 모달, 모바일 listMonth |
| `app/templates/base.html` | 햄버거 메뉴 + `@media` 768/480px 반응형 CSS |
| `app/main.py` | `_on_doc_approved/rejected` 훅 분리, `/api/schedules` CRUD |

---

## Phase 3 — 동적 입력 폼 (업무일지·출장복명서)

**목표:** 문서 작성 시 행 단위 동적 추가/삭제, 파일 첨부, 서버 저장

### 핵심 동작
- doc_new.html에서 문서유형 선택 시 폼이 동적 전환
- JS로 행 추가/삭제 (`addWorkLogRow`, `addTripRow`, `calcTripTotals`)
- POST /doc/new에서 `form.getlist()`로 다중 행 파싱 → WorkLogLine/TripReportLine bulk insert
- 사업자등록증 파일 업로드 → `/file/trip_registration/{id}` 다운로드

### 수정된 파일

| 파일 | 변경 |
|------|------|
| `app/templates/doc_new.html` | WORK_LOG/TRIP_REPORT 옵션 + `<template>` 2개 + JS 함수 |
| `app/main.py` POST /doc/new | WorkLog/Line, TripReport/Line 저장 |
| `app/main.py` doc_view() | 업무일지/출장복명서 데이터 조회 후 템플릿 전달 |
| `app/templates/doc.html` | 업무일지/출장복명서 상세 테이블 렌더링 |

---

## Phase 4 — 품질문서 NAS 연동 + 재개정

**목표:** NAS 볼륨 탐색, PDF 미리보기, 파일 다운로드, 재개정 결재 연동

### 핵심 동작
- `quality_fs.py`가 NAS 마운트(`/nas_quality`)를 재귀 스캔 → 폴더 트리 JSON
- PDF → iframe 인라인 미리보기, 기타 → 다운로드
- 재개정 상신 → Document(QUALITY) 생성 → 결재선 → 승인 시 `_quality_doc_finalize()`

### 신규 파일

| 파일 | 역할 |
|------|------|
| `app/quality_fs.py` | NAS 스캔, 검색, path traversal 방지, 확장자 판별 |
| `app/templates/quality_library.html` | 품질문서 라이브러리 UI |

### 수정된 파일

| 파일 | 변경 |
|------|------|
| `app/main.py` | `/quality/library`, `/quality/file/view\|download`, `POST /quality/revise` |
| `app/main.py` | `_quality_doc_finalize()`, `_on_doc_rejected` 품질문서 처리 |
| `docker-compose.yml` | NAS 마운트 `/nas_quality:ro` + `QUALITY_NAS_ROOT` 환경변수 |
| `app/templates/base.html` | 네비에 '품질문서' 링크 추가, '직급' 링크 제거 |

### 버그 수정
- `scan_tree()` 재귀 시 rel_path가 하위 폴더 기준으로 계산되던 버그 → `_origin` 파라미터로 원점 유지
- 한글 파일명 Content-Disposition 인코딩 에러 → RFC 5987 (`filename*=UTF-8''...`)

---

## Phase 4-v2 — 이력관리·버전비교 UI

**목표:** 문서별 전체 리비전 이력 조회, 버전 간 PDF 비교, 아카이빙 보존

### 핵심 동작

1. **SPA식 레이아웃**: 좌측 NAS 트리 | 우측 PDF 뷰어 + 이력 테이블
2. **버전 비교**: 이력 테이블에서 "PDF 보기" 클릭 → 상단 뷰어에 해당 버전 즉시 로드
3. **검색 자동완성**: 문서번호/제목 입력 → `/api/quality/search` → 드롭다운 → 이력 로드
4. **아카이빙**: 승인 시 `data/quality_archive/{doc_no}/{doc_no}_Rev{N}_{날짜}.ext` 저장

### DB 모델 변경

| 컬럼 | 타입 | 추가 위치 |
|------|------|----------|
| original_filename | String(300) | quality_docs — 상신 시 원본 파일명 |
| archive_path | String(500) | quality_docs — 아카이빙 파일 경로 |

### 신규 API

| 라우트 | 메서드 | 설명 |
|--------|--------|------|
| `/api/quality/history?doc_no=...` | GET | 문서번호별 전 리비전 JSON |
| `/api/quality/search?q=...` | GET | 문서번호/제목 검색 (자동완성) |
| `/quality/revision/pdf?qd_id=...` | GET | 특정 리비전 PDF 인라인 반환 |
| `/quality/archive/download?qd_id=...` | GET | 아카이빙 원본 다운로드 |

### 수정된 파일

| 파일 | 변경 |
|------|------|
| `app/main.py` QualityDoc 모델 | `original_filename`, `archive_path` 컬럼 추가 |
| `app/main.py` migrate_schema() | 새 컬럼 `_ensure_column` 추가 |
| `app/main.py` `_quality_doc_finalize()` | 아카이빙 네이밍 로직 전면 개선 |
| `app/main.py` | 4개 신규 API 라우트 추가 |
| `app/templates/quality_library.html` | SPA식 전면 개편 |

## Phase 5 — 회계 (지역 정규화 · 일월계표 · 미수금대장)

**목표:** 출장복명서 청구 데이터와 수금 데이터를 연결해 자금 흐름·미수금을 관리 (미니 ERP 회계 모듈).

### Phase 5.1 — DB 스키마

| 모델 | 테이블 | 용도 |
|------|--------|------|
| Region | regions | 출장/회계 지역 마스터 (`id`, `name` UNIQUE) |
| Collection | collections | 수금 내역 (`company_name`, `region_name`, `amount`, `collection_date`, `note`) |
| TripReport (확장) | trip_reports | `region_id` FK → regions |

- `migrate_schema()`: 테이블 생성, `trip_reports.region_id` 컬럼, 기본 지역 시드(원주·제천·단양)
- 기존 `APPROVED` 문서 → `APPROVED_FINAL` 일괄 변환 (마이그레이션)

### Phase 5.2 — 출장복명서 UI

- `doc_new.html`: **출장 지역** `<select>` + 「+ 새 지역 추가」 모달
- `GET/POST /api/regions` — 목록·등록 (페이지 새로고침 없이 드롭다운 반영)
- 결재 최종 완료 시 문서 상태 **`APPROVED_FINAL`**
- 회계 청구 집계: `query_trip_billing_lines()` — **APPROVED_FINAL** 출장복명서 라인만 (외상+현금)

### Phase 5.3 — 일월계표 (`/accounting/dashboard`)

- 청구액(출장복명서) vs 수금액(`collections`) 비교 대시보드
- 조회 단위: **일별 / 월별 / 분기 / 연별** (`func.sum`, `group_by`)
  - 월별·분기·연별: 기간 내 **월별** 상세 테이블
  - 일별: 당일 요약 1행
- 네비: **일월계표** · **미수금대장**

### Phase 5.4 — 미수금대장 (`/accounting/ledger`)

- 필터: 기준월, 지역(Region), 업체명
- 컬럼: 전월이월 · 당기발생 · 당기수금 · 미수잔액 (DB `case`/`sum`/`group_by`)
- 행별 **수금 등록** → `POST /api/collections` → 화면 즉시 반영
- **PDF 다운로드** (html2pdf.js, A4 가로)

### 수정·신규 파일

| 파일 | 변경 |
|------|------|
| `app/main.py` | Region, Collection 모델, 회계 집계 헬퍼, 라우트 4개, `APPROVED_FINAL` |
| `app/templates/doc_new.html` | 지역 드롭다운·모달·JS |
| `app/templates/doc.html` | 출장 지역·상세 출장지 표시 |
| `app/templates/accounting_dashboard.html` | 일월계표 UI (신규) |
| `app/templates/accounting_ledger.html` | 미수금대장 UI (신규) |
| `app/templates/base.html` | 일월계표·미수금대장 네비 |

### 배포 시 주의 (재시작)

코드 반영 후 **애플리케이션 컨테이너를 재시작**해야 합니다. 서버 기동 시 `migrate_schema()`가 자동 실행되어 신규 테이블·컬럼이 생성됩니다.

```bash
docker compose down
docker compose up -d --build
```

로컬 개발 시에도 FastAPI 프로세스를 한 번 재시작하세요.

---

## 기타 기능 개선 (알림 고도화)

**목표:** 페이지 이동 없이 알림을 확인하고, 주요 이벤트(결재, 공지, 쪽지) 발생 시 즉각적으로 사용자에게 푸시

### 핵심 동작
- **인페이지 팝업 UI**: `base.html`의 종모양 버튼 클릭 시 드롭다운 팝업으로 최근 알림 표시
- **알림 발생 트리거**:
  - `doc_submit_post()`: 결재 상신 시 결재자에게 알림
  - `doc_approve()`: 승인 시 상신자 + 다음 결재자에게 알림
  - `doc_reject()`: 반려 시 상신자에게 알림
  - `messages_new()`: 쪽지 전송 시 수신자에게 알림
  - `board_new_post()`: 이름에 "공지"가 들어가는 게시판에 새 글 작성 시 전 활성 직원에게 알림

### 추가/수정된 API
- `GET /api/notifications/count` — 배지 업데이트용 (30초 폴링)
- `GET /api/notifications/list` — 팝업 목록 표시용 (최대 30개)
- `POST /api/notifications/read/{id}` — 단일 알림 읽음 처리 및 이동
- `POST /api/notifications/read_all` — 팝업 내 전체 읽음 버튼 처리

---

## UI 개편 — 공통 레이아웃·시스템 관리 (2026-05-19)

**목표:** 그룹웨어형 상단 네비 + 관리 화면 가독성, CSV 등록 안내 강화

### 공통 (`base.html` + `style.css`)

- 헤더 최대 너비 1440px, 메뉴 **한 줄** 배치 (문서·완료·일월계표·미수금·게시판·쪽지·품질·일정·조직도·내정보)
- 메뉴별 SVG 아이콘, 현재 경로 **active** 스타일
- Pretendard Variable (CDN), 슬레이트 톤 + 블루 포인트
- 인라인 CSS 제거 → `app/static/style.css` 일원화

### 시스템 관리

| 파일 | 역할 |
|------|------|
| `templates/partials/admin_nav.html` | 사용자 / 직급 탭 |
| `templates/admin_users.html` | 통계 카드, 사용자 추가·CSV·목록 |
| `templates/admin_grades.html` | 직급 추가·목록·비활성/복구 |
| `templates/admin_user_edit.html` | 사용자 수정 폼 |

- CSV 일괄 등록: 컬럼 표·예시 3행·엑셀 UTF-8 저장 안내 (화면 내)
- `GET /admin` → `303` → `/admin/users`

### 스키마·버그

- `migrate_schema()`: `attachments`에 `uploader_id`, `filesize`, `created_at` 보강 + 기존 행 `creator_id` 백필
- `doc_view`: 첨부 `joinedload` + `selectinload`(출장/업무일지 lines) — 완료 문서 보기 500 방지

### CSV 일괄 등록 (화면 안내)

`admin_users.html`에 컬럼 표·예시 CSV 3행·엑셀 UTF-8·`is_admin` 규칙·초기 PW `changeme123!` 문서화.

---

## Phase 6 — 인프라 고도화·통합 검색·자동 대결·PDF 보안 (2026-05-20)

**목표:** SQLite 한계 대비, 사내 그룹웨어 수준의 보안·검색·결재 연속성·문서 유출 방지.

### Phase 6.1 — DB 접속 추상화 및 세션/IP 보안

| 항목 | 내용 |
|------|------|
| `app/database.py` | `DATABASE_URL`, `create_db_engine()`, `run_schema_migration()` |
| SQLite | `check_same_thread=False`, 기본 `sqlite:///{APP_DATA_DIR}/app.db` |
| PostgreSQL / MariaDB | `pool_pre_ping`, dialect별 `ADD COLUMN` (`inspect` / PRAGMA 분기) |
| `app/security.py` | `SessionIdleMiddleware`, `IpAllowlistMiddleware` |
| 세션 쿠키 | `uid` + `last_activity`, 유휴·절대 만료, API 만료 시 401 JSON |
| 환경 변수 | `SESSION_IDLE_SECONDS`, `SESSION_ABSOLUTE_SECONDS`, `ALLOWED_IPS`, `TRUST_PROXY` |
| 의존성 | `python-dotenv`, `psycopg[binary]`, `pymysql` |
| 템플릿 | `login.html` — `?reason=session_expired` 안내 |

### Phase 6.2 — 글로벌 통합 검색

| 항목 | 내용 |
|------|------|
| `app/search.py` | `run_search()` — documents / posts / attachments |
| 라우트 | `GET /search?q=&tab=all\|document\|post\|attachment` |
| UI | `base.html` 헤더 검색창, `search_results.html`, `style.css` 탭·배지 |
| 권한 | 문서·첨부는 `can_view_doc`와 동일 SQL (작성자·결재자·대결 위임·관리자) |
| 검색 | SQLite `LIKE` / PostgreSQL `ilike`, 카테고리별 LIMIT 20 |

### Phase 6.3 — 부재중 자동 대결

| 항목 | 내용 |
|------|------|
| `app/delegation.py` | `is_user_on_leave_today`, `resolve_effective_approver_id`, `apply_auto_delegation_*` |
| 조건 | `schedules`: `LEAVE`, `ACTIVE`, 오늘 ∈ [start_date, end_date] |
| **대결자 없음** | `delegate_id` 미설정 시 **원 결재자 유지** (건너뛰기·자동승인 없음) |
| 훅 | `doc_submit_post` (상신), `_perform_single_approve` (다음 PENDING) |
| DB | `approvers.original_approver_id` |
| 알림 | `[대결지정] OOO님의 부재로 …` → 대결자 |
| UI | `doc.html` 결재란 `(원결재자 대결)` |
| 로그 | `EventLog` event=`AUTO_DELEGATE` |

### Phase 6.4 — PDF 동적 워터마크

| 항목 | 내용 |
|------|------|
| `app/pdf_watermark.py` | `apply_viewer_watermark()` — reportlab + pypdf |
| 문구 | `열람자: {이름} / 인쇄일시: {KST} / 무단배포 금지` (대각선·연한 회색) |
| 원칙 | 디스크 원본(`data/final/`, NAS) **미수정**, HTTP 응답 바이트만 합성 |
| 적용 | `/doc/{id}/pdf`, 이력 PDF, `/quality/revision/pdf`, NAS PDF view/download |

### Phase 6 신규·수정 파일

| 파일 | 역할 |
|------|------|
| `app/database.py` | 엔진·마이그레이션 |
| `app/security.py` | 미들웨어 |
| `app/search.py` | 통합 검색 |
| `app/delegation.py` | 자동 대결 |
| `app/pdf_watermark.py` | 워터마크 |
| `app/main.py` | 라우트·훅·헬퍼 연동 |
| `app/templates/search_results.html` | 검색 결과 |
| `.env.example` | 환경 변수 샘플 |
| `docker-compose.yml` | Phase 6 env 전달 |
| `requirements.txt` | dotenv, psycopg, pymysql |

---

## 알려진 제한사항 · 후속 작업

| 항목 | 상태 | 비고 |
|------|------|------|
| 관리 POST API | ✅ 구현 (2026-05-19) | 사용자·직급·CSV·PW 초기화 |
| `users.grade` | 문자열 필드 | `grades` 테이블과 이름으로 연동 (FK 아님) |
| `requirements.txt` | 중복 항목 | 상단 비고정 + 하단 pinned 버전 공존 |
| 통합 검색 Full-Text | Phase 6.2는 LIKE/ilike | PostgreSQL `tsvector` 등은 후속 가능 |
| 대결 재검사 | 상신 시점·PENDING 전환 시 | 휴가 종료 후에도 이미 위임된 결재선은 수동 변경 없음 |

상세 라우트 표: [REFERENCE.md](REFERENCE.md)

---

## 기타 수정사항

| 날짜 | 내용 |
|------|------|
| 2026-05-13 | `base.html` 네비에서 직급 링크 제거 (사용자 관리에서 접근 가능) |
| 2026-05-14 | `README.md` 전면 개편, `docs/ARCHITECTURE.md` 신규 작성, `FIXES_SUMMARY.md` 갱신 |
| 2026-05-19 | Phase 5 회계 모듈 문서 반영 (`DEVELOPMENT_PLAN`, `ARCHITECTURE`, `README`, `FIXES_SUMMARY`) |
| 2026-05-19 | UI·관리 화면·CSV 안내·`attachments` 마이그레이션 문서 반영 |

---

## 참고 문서

| 문서 | 설명 |
|------|------|
| `README.md` | 설치, 사용법, 환경변수, CSV, 회계, UI 요약 |
| `docs/ARCHITECTURE.md` | 파일 구조, DB 스키마, 작동 로직·흐름도 |
| `docs/REFERENCE.md` | **전체 HTTP 라우트·상태·모델·migrate·운영** |
| `FIXES_SUMMARY.md` | 초기 버그 수정 + Phase 1~6 변경 이력 |
