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
│       ├── calendar.html      ← 일정관리 (FullCalendar 6)
│       ├── quality_list.html  ← 품질문서 결재 목록
│       ├── quality_doc.html   ← 품질문서 결재 상세
│       ├── quality_library.html ← ★ 품질문서 라이브러리 (NAS 트리 + PDF 뷰어 + 이력)
│       ├── admin_users.html   ← 사용자 관리
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
│   ├── db.sqlite3             ← SQLite 데이터베이스
│   ├── uploads/               ← 문서별 첨부파일
│   ├── final/                 ← 최종 승인 PDF
│   ├── trash/                 ← 소프트 삭제 파일
│   └── quality_archive/       ← 품질문서 리비전 아카이빙
│
└── docs/                      ← 프로젝트 문서
    ├── ARCHITECTURE.md        ← 이 파일
    └── DEVELOPMENT_PLAN.md    ← 개발 계획 및 진행 기록
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
        │               └── trip_report_lines (trip_report_id)
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
| status | String | DRAFT → SUBMITTED → IN_REVIEW → APPROVED / REJECTED |
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
| filename | String | 원래 파일명 |
| filepath | String | 서버 저장 경로 |
| filesize | Integer | 바이트 |

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

#### trip_reports / trip_report_lines (출장복명서)
| 컬럼 (trip_report) | 설명 |
|------|------|
| document_id | FK → documents |
| author_id | FK → users |
| destination | 출장지 |
| purpose | 출장 목적 |
| registration_file_path | 사업자등록증 파일 경로 |

| 컬럼 (trip_report_line) | 설명 |
|------|------|
| trip_report_id | FK → trip_reports |
| date_str | 일자 |
| description | 내용 |
| supply_amount | 공급가액 |
| tax_amount | 세액 |
| total_amount | 합계 |

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

### 페이지 라우트 (HTML 반환)

| URL | 메서드 | 화면 | 설명 |
|-----|--------|------|------|
| `/login` | GET/POST | 로그인 | 세션 쿠키 발급 |
| `/logout` | GET | 로그아웃 | 쿠키 삭제 |
| `/` | GET | 리다이렉트 | → `/dashboard` |
| `/dashboard` | GET | 대시보드 | 내 문서 + 결재 대기 목록 |
| `/doc/new` | GET/POST | 새 문서 | 문서유형 선택 → 동적 폼 |
| `/doc/{id}` | GET | 문서 상세 | 결재 현황, 승인/반려 버튼 |
| `/doc/{id}/submit` | GET/POST | 결재선 지정 | 결재자 선택 → 상신 |
| `/doc/{id}/approve` | POST | 승인 | 결재 처리 |
| `/doc/{id}/reject` | POST | 반려 | 반려 처리 |
| `/doc/batch_approve` | POST | 일괄 승인 | 체크박스 선택 문서 일괄 |
| `/completed` | GET | 완료 문서 | 검색 (문서번호/제목/상신자/날짜) |
| `/calendar` | GET | 캘린더 | FullCalendar 월/주/일/목록 |
| `/quality` | GET | 품질문서 목록 | QUALITY 유형 문서 리스트 |
| `/quality/library` | GET | 품질문서 라이브러리 | NAS 트리 + PDF 뷰어 + 이력 |
| `/quality/doc/{id}` | GET | 품질문서 상세 | |
| `/boards` | GET | 게시판 목록 | |
| `/board/{id}` | GET | 게시판 | 글 목록 |
| `/board/{id}/new` | GET | 게시글 작성 화면 |
| `/board/{id}/new` | POST | 게시글 저장 (공지사항일 경우 알림 트리거) | |
| `/post/{id}` | GET | 게시글 상세 | |
| `/messages` | GET | 쪽지함 | |
| `/message/{id}` | GET | 쪽지 상세 | |
| `/me` | GET | 내 정보 | |
| `/org` | GET | 조직도 | |
| `/notifications` | GET | 알림 | |
| `/change-password` | GET/POST | 비밀번호 변경 | |
| `/admin/users` | GET | 사용자 관리 | 관리자 전용 |
| `/admin/grades` | GET | 직급 관리 | 관리자 전용 |

### API 라우트 (JSON 반환)

| URL | 메서드 | 설명 |
|-----|--------|------|
| `/api/notifications/count` | GET | 읽지 않은 알림 개수 |
| `/api/notifications/list` | GET | 사용자 알림 목록 반환 (팝업용) |
| `/api/notifications/read/{id}` | POST | 단일 알림 읽음 처리 |
| `/api/notifications/read_all` | POST | 전체 알림 읽음 처리 |
| `/api/events` | GET | 캘린더 이벤트 (레거시) |
| `/api/events` | POST | 이벤트 생성 (레거시) |
| `/api/events/{id}/delete` | POST | 이벤트 삭제 (레거시) |
| `/api/schedules` | GET | 일정 목록 (FullCalendar JSON) |
| `/api/schedules` | POST | 일정 생성 |
| `/api/schedules/{id}/delete` | POST | 일정 취소 |
| `/api/quality/history?doc_no=...` | GET | 품질문서 리비전 이력 |
| `/api/quality/search?q=...` | GET | 품질문서 검색 (자동완성) |

### 파일 서빙 라우트

| URL | 설명 |
|-----|------|
| `/doc/{id}/pdf` | 최종 승인 PDF |
| `/file/original/{id}` | 원본 첨부 다운로드 |
| `/file/attachment/{id}` | 첨부파일 다운로드 |
| `/file/trip_registration/{id}` | 사업자등록증 다운로드 |
| `/quality/file/view?path=...` | NAS 파일 인라인 보기 (PDF) |
| `/quality/file/download?path=...` | NAS 파일 다운로드 |
| `/quality/revision/pdf?qd_id=...` | 품질문서 리비전 PDF |
| `/quality/archive/download?qd_id=...` | 품질문서 아카이빙 원본 다운로드 |

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
   │                          │                      │  │  status: APPROVED  │
   │                          │                      │  │  최종 PDF 생성     │
   │                          │                      │  │  후처리 훅 실행    │
   │                          │                      │  └────────────────────┘
```

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

---

## 7. 인증/세션

- 로그인 시 `itsdangerous`로 서명된 쿠키(`session_token`) 발급
- 모든 라우트에서 `get_current_user()` 의존성으로 인증 확인
- 첫 로그인 시 `must_change_pw = True`이면 비밀번호 변경 페이지로 강제 이동
- 비밀번호는 `passlib` (bcrypt) 해시 저장

---

## 8. 모바일 반응형

`base.html`에 두 개의 브레이크포인트:

| 너비 | 변경사항 |
|------|----------|
| ≤ 768px | 햄버거 메뉴, 테이블 가로 스크롤, 폼 1열 배치, 캘린더 목록 뷰 |
| ≤ 480px | 브랜드 축소, 버튼/입력 최소 너비 축소 |

품질문서 라이브러리: 768px 이하에서 좌측 트리와 우측 본문이 세로 배치로 전환.

---

## 9. 외부 라이브러리 (CDN)

| 라이브러리 | 버전 | 용도 | 사용 위치 |
|-----------|------|------|----------|
| FullCalendar | 6.1.11 | 캘린더 뷰 | calendar.html |

나머지는 모두 Vanilla JS + Jinja2 서버 렌더링.

---

## 10. 환경별 설정

| 설정 | 기본값 | 변경 방법 |
|------|--------|----------|
| DB 경로 | `/data/db.sqlite3` | 코드 내 `DATA_DIR` |
| 업로드 경로 | `/data/uploads/` | 코드 내 `DATA_DIR` |
| NAS 마운트 | `/nas_quality` | 환경변수 `QUALITY_NAS_ROOT` |
| 세션 키 | `change-me-long-random` | 환경변수 `APP_SECRET` |
| 관리자 ID/PW | `admin` / `admin1234!` | 환경변수 `APP_ADMIN_ID` / `APP_ADMIN_PW` |
| 포트 | 8080 (외부) → 8000 (내부) | docker-compose.yml `ports` |
