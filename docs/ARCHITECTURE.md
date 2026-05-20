# 시스템 아키텍처 및 작동 로직

> 이 문서는 (주)영동환경이앤텍 전자결재 시스템의 **전체 구조**, **파일 역할**, **DB 스키마**, **화면별 라우트**, **핵심 작동 로직**을 설명합니다.
> 코드를 처음 보는 사람도 이해할 수 있도록 작성되었습니다.

---

## 1. 프로젝트 파일 구조

```
approval_mvp/
│
├── docker-compose.yml        ← Docker 서비스 정의 (포트, 환경변수, 볼륨 마운트)
├── Dockerfile                ← Python 3.11 이미지 빌드 설정
├── requirements.txt          ← Python 패키지 목록
│
├── app/                      ← 애플리케이션 소스 (컨테이너의 /app에 마운트)
│   ├── main.py               ← ★ 핵심: FastAPI 앱, 모든 라우트, DB 모델, 비즈니스 로직
│   ├── quality_fs.py          ← NAS 볼륨 스캔 서비스 (품질문서용)
│   ├── __init__.py            ← Python 패키지 선언
│   │
│   ├── static/
│   │   └── style.css          ← 공통 CSS
│   │
│   └── templates/             ← Jinja2 HTML 템플릿
│       ├── base.html          ← 레이아웃 (헤더, 네비게이션, 반응형 CSS)
│       ├── login.html         ← 로그인 페이지
│       ├── dashboard.html     ← 메인 대시보드 (내 문서 + 결재 문서 목록)
│       ├── doc_new.html       ← 새 문서 작성 (문서유형별 동적 폼)
│       ├── doc.html           ← 문서 상세 보기 (결재 현황 포함)
│       ├── doc_submit.html    ← 결재선 지정 + 상신
│       ├── doc_detail.html    ← 문서 상세 (결재자 선택 포함)
│       ├── completed.html     ← 완료 문서 검색
│       ├── accounting_dashboard.html ← 일월계표 (청구 vs 수금)
│       ├── accounting_ledger.html    ← 미수금대장 (수금 등록·PDF)
│       ├── calendar.html      ← 일정관리 (FullCalendar 6)
│       ├── quality_list.html  ← 품질문서 결재 목록
│       ├── quality_doc.html   ← 품질문서 결재 상세
│       ├── quality_library.html ← ★ 품질문서 라이브러리 (NAS 트리 + PDF 뷰어 + 이력)
│       ├── partials/
│       │   └── admin_nav.html   ← 관리 탭 (사용자/직급)
│       ├── admin_users.html   ← 사용자 관리 (CSV 일괄 등록 안내 포함)
│       ├── admin_grades.html  ← 직급 관리
│       ├── admin_user_edit.html ← 사용자 수정
│       ├── board_list_all.html ← 게시판 목록
│       ├── board_view.html    ← 게시판 글 목록
│       ├── board_new.html     ← 게시글 작성
│       ├── post_view.html     ← 게시글 상세
│       ├── messages.html      ← 쪽지함
│       ├── message_view.html  ← 쪽지 상세
│       ├── me.html / my_profile.html ← 내 정보
│       ├── change_password.html ← 비밀번호 변경
│       ├── notifications.html ← 알림 목록
│       ├── org_chart.html     ← 조직도
│       └── submit.html        ← 상신 확인
│
├── data/                      ← 영구 데이터 (컨테이너의 /data에 마운트)
│   ├── app.db                 ← SQLite 데이터베이스
│   ├── uploads/               ← 문서별 첨부파일
│   ├── final/                 ← 최종 승인 PDF
│   ├── trash/                 ← 소프트 삭제 파일
│   └── quality_archive/       ← 품질문서 리비전 아카이빙
│
└── docs/                      ← 프로젝트 문서
    ├── ARCHITECTURE.md        ← 이 파일 (구조·로직)
    ├── REFERENCE.md           ← 전체 라우트·상태·DB·운영 (상세 목록)
    └── DEVELOPMENT_PLAN.md    ← 개발 계획 및 진행 기록
│
└── scripts/                   ← 점검·진단 스크립트 (check_db, test_pages 등)
```

---

## 2. Docker 구성

```
┌─────────────────────────────────────────┐
│  Synology NAS (Host)                    │
│                                         │
│  ./app ──────→ /app (소스코드)          │
│  ./data ─────→ /data (DB + 업로드)      │
│  /volume1/품질문서/... ──→ /nas_quality  │
│                           (읽기 전용)    │
│                                         │
│  ┌──────────────────────┐               │
│  │  Docker Container    │               │
│  │  approval_mvp        │               │
│  │                      │               │
│  │  uvicorn main:app    │               │
│  │  :8000 (내부)        │               │
│  └──────────────────────┘               │
│           │                             │
│     Port 8080 ←→ 8000                   │
└─────────────────────────────────────────┘
```

- `--reload` 모드: `./app` 폴더가 마운트되어 있어서 파일 수정 시 자동 재시작
- NAS 품질문서 볼륨: **읽기 전용(ro)** 마운트 → 웹에서 수정 불가, 열람/다운로드만 가능

---

## 3. 데이터베이스 스키마 (SQLAlchemy 모델)

### 핵심 테이블 관계도

```
users ──┬── documents (creator_id)
        │       │
        │       ├── approvers (doc_id) ←── users (approver_id)
        │       ├── attachments (doc_id)
        │       ├── quality_docs (document_id)
        │       ├── worklogs (document_id)
        │       │       └── worklog_lines (worklog_id)
        │       └── trip_reports (document_id)
        │               ├── region_id → regions
        │               └── trip_report_lines (trip_report_id)
        │
        ├── regions (지역 마스터)
        └── collections (수금 내역, region_name ↔ regions.name 텍스트 매칭)
        │
        ├── schedules (user_id, document_id)
        ├── messages (sender_id, receiver_id)
        ├── notifications (user_id)
        └── calendar_events (user_id)

grades ──── users (grade_id)
boards ──── posts (board_id) ←── users (author_id)
```

### 테이블별 설명

#### users (사용자)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | PK | |
| username | String | 로그인 ID |
| password_hash | String | bcrypt 해시 |
| name | String | 이름 |
| dept | String | 부서 |
| grade_id | FK → grades | 직급 |
| is_admin | Boolean | 관리자 여부 |
| is_active | Boolean | 활성 여부 |
| must_change_pw | Boolean | 첫 로그인 시 비번 변경 강제 |
| delegate_id | FK → users | 대결자 |

#### grades (직급)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | PK | |
| name | String | 직급명 (사원, 대리, 과장...) |
| level | Integer | 직급 순서 (1=최상위) |
| is_active | Boolean | 활성 여부 |

#### documents (문서/결재 건)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | PK | |
| title | String | 제목 |
| body | Text | 본문 |
| creator_id | FK → users | 작성자 |
| doc_type | String | 유형: GENERAL, LEAVE, EXPENSE, QUALITY, WORK_LOG, TRIP_REPORT |
| doc_no | String | 문서번호 (품질문서용) |
| rev | Integer | 리비전 번호 |
| status | String | DRAFT → IN_REVIEW → APPROVED_FINAL (완료) / REJECTED. 레거시 APPROVED는 마이그레이션 시 APPROVED_FINAL |
| mode | String | SEQUENTIAL (순차) / PARALLEL (병렬) |
| leave_start, leave_end, leave_kind, leave_hours | String | 휴가 관련 필드 |
| expense_total | Integer | 지출 합계 |
| created_at, updated_at | DateTime | 시간 |

#### approvers (결재선)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | PK | |
| doc_id | FK → documents | 문서 |
| approver_id | FK → users | 결재자 |
| order_no | Integer | 결재 순서 (순차 모드용) |
| action | String | PENDING / APPROVED / REJECTED / WAITING |
| comment | Text | 결재 의견 |
| acted_at | DateTime | 결재 시각 |

#### attachments (첨부파일)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | PK | |
| doc_id | FK → documents | 문서 |
| uploader_id | FK → users | 업로드한 사용자 |
| filename | String | 원래 파일명 |
| filepath | String | 서버 저장 경로 |
| filesize | Integer | 바이트 (기본 0) |
| created_at | DateTime | 업로드 시각 |

> 구 DB에는 `uploader_id` 등이 없을 수 있음. 기동 시 `migrate_schema()`가 컬럼 추가 후, 기존 행은 `documents.creator_id`로 백필.

#### regions (지역 마스터) — Phase 5
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | PK | |
| name | String(50) UNIQUE | 원주·제천·단양 등 (시드) |

#### collections (수금) — Phase 5
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | PK | |
| company_name | String | 업체명 |
| region_name | String | regions.name 과 텍스트 매칭 |
| amount | Integer | 수금액 |
| collection_date | String(10) | YYYY-MM-DD |
| note | Text | 비고 |

#### trip_report_lines (출장 세금계산서 행)
| 컬럼 | 설명 |
|------|------|
| line_date | 회계 집계 기준일 |
| company_name | 미수금·대장 키 |
| credit_amount / cash_amount | 외상 / 현금 |
| volume_no, doc_number, details | 세부 |

#### schedules (일정)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | PK | |
| title | String | 일정 제목 |
| start_date | Date | 시작일 |
| end_date | Date | 종료일 |
| type | String | LEAVE / COMPANY / TEAM_1~5 |
| user_id | FK → users | 등록자 |
| status | String | ACTIVE / CANCELLED |
| document_id | FK → documents | 연결된 결재 문서 (nullable) |
| color | String | 캘린더 표시 색상 |
| memo | Text | 메모 |

#### worklogs / worklog_lines (업무일지)
| 컬럼 (worklog) | 설명 |
|------|------|
| document_id | FK → documents |
| author_id | FK → users |
| work_date | 작업일 |
| team_name | 팀명 |
| note | 비고 |

| 컬럼 (worklog_line) | 설명 |
|------|------|
| worklog_id | FK → worklogs |
| company_name | 업체명 |
| task_content | 업무내용 |
| mileage | 주행거리 |
| order_no | 수주번호 |

#### regions (지역 마스터 — Phase 5)
| 컬럼 | 설명 |
|------|------|
| id | PK |
| name | 지역명 (UNIQUE), 예: 원주·제천·단양 |

#### collections (수금 — Phase 5)
| 컬럼 | 설명 |
|------|------|
| id | PK |
| company_name | 업체명 |
| region_name | 지역명 (`regions.name`과 일치해야 등록 가능) |
| amount | 수금액 (원) |
| collection_date | 수금일 (YYYY-MM-DD) |
| note | 비고 |

#### trip_reports / trip_report_lines (출장복명서)
| 컬럼 (trip_report) | 설명 |
|------|------|
| doc_id | FK → documents |
| user_id | FK → users |
| trip_date | 출장일자 |
| region_id | FK → regions (출장 지역, nullable) |
| destination | 출장지 상세 |
| purpose | 출장 목적 |
| registration_file_path | 사업자등록증 파일 경로 |

| 컬럼 (trip_report_line) | 설명 |
|------|------|
| trip_report_id | FK → trip_reports |
| line_date | 일자 |
| company_name | 업체명 |
| details | 내역 |
| credit_amount | 외상금액 |
| cash_amount | 현금금액 |
| order_no | 행 순서 |

**회계 청구액:** `credit_amount + cash_amount` (문서 `status = APPROVED_FINAL` 인 라인만 집계)

#### quality_docs (품질문서 이력)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | PK | |
| doc_no | String | 문서번호 (예: QP-01-03) |
| title | String | 제목 |
| rev_no | Integer | 리비전 번호 (1, 2, 3...) |
| file_path | String | PDF/뷰어용 파일 경로 |
| original_filename | String | 상신 시 원본 파일명 |
| archive_path | String | 아카이빙된 파일 경로 |
| document_id | FK → documents | 연결된 결재 문서 |
| uploader_id | FK → users | 등록자 |
| status | String | PENDING / ACTIVE / SUPERSEDED / REJECTED |
| created_at, updated_at | DateTime | |

**status 흐름:**
```
PENDING (결재 중) → ACTIVE (현행, 승인됨) → SUPERSEDED (다음 버전 승인 시)
                  → REJECTED (반려)
```

---

## 4. 화면(라우트) 맵

> **전체 목록(70+ 라우트, 관리 POST 미구현 표기):** [REFERENCE.md](REFERENCE.md)

### 요약

| 구분 | 대표 URL | 인증 |
|------|----------|------|
| 결재 | `/dashboard`, `/doc/new`, `/doc/{id}`, `/completed` | 로그인 |
| 회계 | `/accounting/dashboard`, `/accounting/ledger`, `/api/collections` | 로그인 |
| 품질 | `/quality/library`, `/api/quality/*`, `/quality/revise` | 로그인 |
| 협업 | `/boards`, `/messages`, `/calendar`, `/org` | 로그인 |
| 알림 | `/api/notifications/*` | 로그인 |
| 관리 | `/admin/users`, `/admin/grades` | **관리자** (`require_admin`) |

### 관리자 API

| 구분 | 상태 |
|------|------|
| GET `/admin`, `/admin/users`, `/admin/grades`, `/admin/users/{id}/edit` | ✅ |
| POST 사용자 추가·CSV·수정·비활성·PW초기화 | ✅ |
| POST 직급 추가·비활성·복구 | ✅ |

- 직급은 `users.grade`(문자열)에 저장. 비활성화 시 해당 이름 사용자의 직급 필드 초기화.
- 마지막 활성 관리자·본인 계정 보호 로직 포함.

### 파일·미리보기 라우트 (추가)

| URL | 설명 |
|-----|------|
| `/preview/original/{id}`, `/preview/history/{id}` | 미리보기 |
| `/file/history/{id}` | 이력 파일 |
| `/file/message_attachment/{id}` | 쪽지 첨부 |
| `/messages/{id}` | 쪽지 상세 (별칭 `/message/{id}`) |

---

## 5. 핵심 작동 로직

### 5.1 결재 흐름 (순차 모드 기준)

```
[상신자]                    [결재자 1]              [결재자 2]              [시스템]
   │                          │                      │                      │
   ├─ 문서 작성 ──────────────┤                      │                      │
   ├─ 결재선 지정 (순차) ─────┤                      │                      │
   ├─ 상신 ───────────────────┤                      │                      │
   │                          │                      │                      │
   │  status: IN_REVIEW       │                      │                      │
   │  결재자1: PENDING        │                      │                      │
   │  결재자2: WAITING ←(아직 차례 아님)              │                      │
   │                          │                      │                      │
   │                  승인 ───┤                      │                      │
   │                          │  결재자1: APPROVED   │                      │
   │                          │  결재자2: PENDING ←(차례)                   │
   │                          │                      │                      │
   │                          │              승인 ───┤                      │
   │                          │                      │  결재자2: APPROVED   │
   │                          │                      │                      │
   │                          │                      │  ┌─ 전원 승인 감지 ──┤
   │                          │                      │  │                    │
   │                          │                      │  │  status: APPROVED_FINAL │
   │                          │                      │  │  최종 PDF 생성          │
   │                          │                      │  │  후처리 훅 실행         │
   │                          │                      │  └─────────────────────────┘
```

**완료 상태:** `APPROVED_FINAL` (레거시 `APPROVED`는 마이그레이션 시 변환). `is_doc_final()` / `DOC_FINAL_STATUSES`로 완료 문서 판별.

**코드 위치:** `main.py` → `doc_approve()` → `update_doc_status_after_action()` → `_on_doc_approved()`

### 5.2 결재 후처리 훅 (`_on_doc_approved`)

문서 유형에 따라 결재 완료 시 자동으로 추가 작업을 수행합니다.

| 문서 유형 | 후처리 동작 |
|-----------|-------------|
| **LEAVE (휴가)** | Schedule 테이블에 일정 자동 생성 → 캘린더에 표시 |
| **QUALITY (품질문서)** | `_quality_doc_finalize()` 실행 (아래 참조) |

반려 시 (`_on_doc_rejected`):
| 문서 유형 | 후처리 동작 |
|-----------|-------------|
| **LEAVE** | 연결된 Schedule의 status → CANCELLED |
| **QUALITY** | 연결된 QualityDoc의 status → REJECTED |

### 5.8 회계 집계 (Phase 5)

```
[출장복명서 결재 완료]                    [회계 화면]
   APPROVED_FINAL                          │
   TripReportLine                          ├─ 일월계표: 기간별 SUM(청구), SUM(수금)
   (line_date, credit+cash)                │     query_trip_billing_lines()
                                           │
[수금 입력]                                └─ 미수금대장: 업체×지역
   POST /api/collections                        전월이월 + 당기발생 − 당기수금
   collections 테이블                          _build_ledger_rows() — DB case/sum/group_by
```

| 화면 | 집계 기준일 | 청구 원천 | 수금 원천 |
|------|-------------|-----------|-----------|
| 일월계표 | `line_date` / `collection_date` | APPROVED_FINAL TripReportLine | Collection |
| 미수금대장 | 기준월 | 동일 (월 구간 + 이전 누적) | 동일 |

**지역 정규화:** 출장은 `regions.id`(FK). 수금은 `collections.region_name` = `regions.name` 텍스트 매칭.

### 5.3 품질문서 재개정 전체 흐름

```
[사용자]                              [시스템]                           [DB]
   │                                    │                                │
   ├─ 품질문서 라이브러리 접속 ─────────┤                                │
   │  (NAS 트리 탐색, PDF 미리보기)     │                                │
   │                                    │                                │
   ├─ "재개정 상신" 클릭 ──────────────┤                                │
   │  (문서번호: QP-01-03)              │                                │
   │  (파일 업로드: 개정판.hwp)         │                                │
   │                                    │                                │
   │                           POST /quality/revise                      │
   │                                    │                                │
   │                                    ├─ Document 생성 (QUALITY) ─────→│
   │                                    ├─ Attachment 저장 ─────────────→│
   │                                    ├─ QualityDoc 생성 ────────────→│
   │                                    │   (rev_no = 이전+1)            │
   │                                    │   (status = PENDING)           │
   │                                    │                                │
   │←──── 결재선 지정 페이지로 이동 ────┤                                │
   │                                    │                                │
   ├─ 결재선 지정 → 상신 ─────────────┤                                │
   │                                    │                                │
   │    ... 결재 진행 ...               │                                │
   │                                    │                                │
   │                           최종 승인 시:                             │
   │                           _quality_doc_finalize()                   │
   │                                    │                                │
   │                                    ├─ QualityDoc.status → ACTIVE ──→│
   │                                    ├─ 이전 ACTIVE → SUPERSEDED ───→│
   │                                    ├─ 파일 아카이빙 ───────────────→│
   │                                    │  (quality_archive/QP-01-03/    │
   │                                    │   QP-01-03_Rev2_20260514.hwp)  │
   │                                    │                                │
   │  이력 테이블에 새 버전 표시 ←──────┤                                │
```

**아카이빙 네이밍 규칙:**
```
data/quality_archive/{doc_no}/{doc_no}_Rev{N}_{YYYYMMDD}.{ext}

예: data/quality_archive/QP-01-03/QP-01-03_Rev2_20260514.hwp
```

### 5.4 품질문서 버전 비교 (UI 동작)

```
1. 사용자가 품질문서 라이브러리 접속
2. 검색바에 "QP-01" 입력 → 자동완성 드롭다운 표시
3. "QP-01-03" 클릭 → /api/quality/history?doc_no=QP-01-03 호출
4. 이력 테이블 렌더링:

   ┌──────┬────────────┬────────┬──────┬────────────┬──────────────────────┐
   │ Rev  │ 제목       │ 상태   │ 등록자│ 날짜       │ 액션                 │
   ├──────┼────────────┼────────┼──────┼────────────┼──────────────────────┤
   │ Rev.3│ 품질매뉴얼 │ 현행   │ 홍길동│ 2026-05-14 │ [PDF보기][원본↓][결재]│
   │ Rev.2│ 품질매뉴얼 │ 구버전 │ 홍길동│ 2026-05-10 │ [PDF보기][원본↓][결재]│
   │ Rev.1│ 품질매뉴얼 │ 구버전 │ 김철수│ 2026-04-01 │ [PDF보기][원본↓][결재]│
   └──────┴────────────┴────────┴──────┴────────────┴──────────────────────┘

5. "PDF 보기" 클릭 → 상단 iframe에 해당 버전 PDF 로드
6. 다른 버전 "PDF 보기" 클릭 → 뷰어가 즉시 교체 (버전 비교)
7. "원본↓" 클릭 → 해당 버전의 hwp/xls 등 원본 파일 다운로드
```

### 5.5 일정관리 자동 연동

```
[휴가 결재 승인]
       │
       ▼
_on_doc_approved()
       │
       ├─ Schedule 생성
       │   type: "LEAVE"
       │   start_date: 문서의 leave_start
       │   end_date: 문서의 leave_end
       │   document_id: 문서 ID (역추적 가능)
       │
       ▼
캘린더 페이지에서 FullCalendar가
/api/schedules 로 JSON fetch →
Schedule + CalendarEvent 통합 표시
```

### 5.6 NAS 볼륨 스캔 (quality_fs.py)

```python
scan_tree(NAS_ROOT)
  → 재귀적으로 폴더를 순회
  → 각 파일/폴더의 {name, rel_path, is_dir, ext, size} 반환
  → rel_path는 항상 NAS_ROOT 기준 (하위 폴더도 원점 유지)
  → 템플릿에서 트리 렌더링에 사용

resolve_file_path(rel_path)
  → rel_path를 NAS_ROOT와 결합하여 절대경로 반환
  → path traversal 공격 방지 (../ 등 차단)
```

### 5.7 알림 시스템 (Notification)

사용자 경험 향상을 위해 페이지 이동 없이 상단 종모양(Bell) 아이콘 클릭 시 **인페이지 드롭다운 팝업**으로 알림을 제공합니다.

| 알림 발생 이벤트 (트리거) | 수신자 | 알림 메시지 예시 |
|-------------------------|--------|------------------|
| **결재 상신** | 해당 결재자 (순차: 첫번째, 병렬: 전원) | `[결재요청] OOO님이 「제목」을 상신했습니다` |
| **결재 승인 (중간)** | 상신자 및 다음 결재자 | 상신자: `[승인]`, 다음 결재자: `[결재요청]` |
| **결재 최종 승인** | 상신자 | `[승인완료] 「제목」이 최종 승인되었습니다` |
| **결재 반려** | 상신자 | `[반려] OOO님이 「제목」을 반려했습니다` |
| **쪽지 발송** | 수신자 | `[쪽지] OOO님이 쪽지를 보냈습니다` |
| **공지사항 등록** | 작성자 제외 전 활성 직원 | `[공지사항] 제목` |

- **동작 방식**: 
  - 30초마다 `/api/notifications/count` 폴링하여 배지 숫자 갱신
  - 종모양 클릭 시 `/api/notifications/list` 호출하여 드롭다운 렌더링
  - 개별 알림 클릭 시 `/api/notifications/read/{id}` (읽음 처리) 후 해당 링크로 리다이렉트

---

## 6. 데이터베이스 마이그레이션

시스템은 `migrate_schema()` 함수를 서버 시작 시 자동 실행합니다.

```
서버 시작 → migrate_schema()
  → Base.metadata.create_all() : 테이블이 없으면 생성
  → _ensure_column() : 기존 테이블에 새 컬럼이 없으면 ALTER TABLE ADD COLUMN
  → _ensure_table_exists() : 테이블 존재 여부 확인
```

**주의:** SQLite는 컬럼 삭제/타입 변경이 불가하므로, 추가만 수행합니다.
기존 데이터는 절대 삭제되지 않습니다.

**`migrate_schema()` 전체 항목:**

| 단계 | 내용 |
|------|------|
| 1 | `Base.metadata.create_all()` |
| 2 | `documents` — doc_type, rev, base_doc_id, status, mode, leave_*, overtime_*, cert_*, expense_total, created_at, updated_at |
| 3 | `users` — must_change_pw, is_admin, grade_id, delegate_id |
| 4 | `grades` — level, is_active |
| 5 | `attachments` — uploader_id, filesize, created_at + `UPDATE` uploader_id ← creator_id |
| 6 | `schedules` — color, memo, document_id |
| 7 | `worklogs` — work_date |
| 8 | `trip_reports` — destination, purpose, registration_file_path, **region_id** |
| 9 | `quality_docs` — status, uploader_id, original_filename, archive_path |
| 10 | `collections` — company_name, region_name, amount, collection_date, note |
| 11 | `_seed_default_regions()` — 원주·제천·단양 |
| 12 | `UPDATE documents SET status='APPROVED_FINAL' WHERE status='APPROVED'` |

실패 시 로그: `[migrate] migrate_schema failed: ...` (앱은 기동되나 스키마 불일치 가능).

---

## 7. 인증/세션

- 로그인 시 `itsdangerous`로 서명된 쿠키(`session_token`) 발급
- 모든 라우트에서 `get_current_user()` 의존성으로 인증 확인
- 첫 로그인 시 `must_change_pw = True`이면 비밀번호 변경 페이지로 강제 이동
- 비밀번호는 `passlib` (bcrypt) 해시 저장

---

## 8. 프론트엔드 UI

### 공통 스타일 (`app/static/style.css`)

- CSS 변수(색·간격·그림자), 카드·버튼·테이블·배지·알림 팝업
- **관리 화면** 전용: `.admin-page`, `.admin-tabs`, `.admin-stats`, `.admin-section`, CSV 안내 테이블·코드 블록

### 레이아웃 (`base.html`)

- Sticky 헤더, 브랜드 + **한 줄** `header-nav` (max-width 1440px) + 알림·로그아웃
- `request.url.path` 기준 메뉴 `active` 클래스
- 본문 `container` (max-width 1200px)

### 모바일 반응형

| 너비 | 변경사항 |
|------|----------|
| ≤ 1100px | 네비 라벨 숨김, 아이콘만 표시 |
| ≤ 768px | 햄버거 메뉴, 테이블 가로 스크롤, 폼 1열, 관리 그리드 1열 |
| ≤ 480px | 알림 팝업 너비 조정 |

품질문서 라이브러리: 768px 이하에서 좌측 트리와 우측 본문이 세로 배치로 전환.

---

## 9. 외부 라이브러리 (CDN)

| 라이브러리 | 버전 | 용도 | 사용 위치 |
|-----------|------|------|----------|
| Pretendard | 1.3.9 | 한글 UI 폰트 | `base.html` |
| FullCalendar | 6.1.11 | 캘린더 뷰 | calendar.html |
| html2pdf.js | — | PDF 다운로드 | accounting_ledger.html |

나머지는 Vanilla JS + Jinja2 서버 렌더링. 메뉴·관리 화면 아이콘은 인라인 SVG.

### UI 클래스 (`style.css` 요약)

| 클래스 | 용도 |
|--------|------|
| `.app-header`, `.header-nav`, `.nav-item.active` | 상단 네비 |
| `.admin-page`, `.admin-tabs`, `.admin-stats` | 관리 화면 |
| `.admin-section`, `.admin-callout`, `.admin-csv-sample` | 관리 카드·CSV 안내 |
| `.card`, `.btn.primary`, `.tag-*` | 공통 컴포넌트 |

---

## 10. 환경별 설정

| 설정 | 기본값 | 변경 방법 |
|------|--------|----------|
| DB 경로 | `/data/app.db` | 코드 내 `DB_PATH` |
| 업로드 경로 | `/data/uploads/` | 코드 내 `DATA_DIR` |
| NAS 마운트 | `/nas_quality` | 환경변수 `QUALITY_NAS_ROOT` |
| 세션 키 | `change-me-long-random` | 환경변수 `APP_SECRET` |
| 관리자 ID/PW | `admin` / `admin1234!` | 환경변수 `APP_ADMIN_ID` / `APP_ADMIN_PW` |
| 포트 | 8080 (외부) → 8000 (내부) | docker-compose.yml `ports` |
