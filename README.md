# (주)영동환경이앤텍 — 전자결재 시스템

> Synology NAS Docker 기반 내부망 전용 전자결재 + 일정관리 + 품질문서 관리 시스템

---

## 한눈에 보기

| 항목 | 내용 |
|------|------|
| 백엔드 | Python 3.11 / FastAPI |
| 데이터베이스 | SQLite 기본 (`./data/app.db`) · PostgreSQL / MariaDB 선택 (`DATABASE_URL`) |
| 프론트엔드 | Jinja2 템플릿 + Vanilla JS + 공통 CSS (`style.css`, Pretendard 폰트) |
| 배포 | Docker Compose → Synology NAS |
| 접속 주소 | `http://NAS_IP:8080` |
| 기본 관리자 | ID: `admin` / PW: `admin1234!` |

---

## 주요 기능

### 1. 전자결재
- 문서 작성 → 결재선 지정 → 상신 → 승인/반려
- **직급 순서 기반 결재**: 시스템 관리에서 정한 직급 순서(위=높은 직급)대로, **낮은 직급부터** 결재. 상신 시 결재자 선택 순서와 무관하게 자동 정렬
- 일반 문서: 순차(직급순) 또는 병렬(전원 동시) 선택
- **업무일지**: **평일** 휴가·제외 직급 제외 **전원** 작성 · **주말** 출장(측정팀 일정)·주말근무·근무표 등록 **근무자만** 작성. 결재는 **동일 지사** **차장~대표** 직급순(동직급 병렬), 작성자는 작성완료
- **출장복명서**: **관리팀·측정팀** 소속 전원이 직급순으로 자동 결재선 (작성자 제외, 수동 선택 없음)
- 문서 유형: 일반기안, 휴가, 지출결의, 연장근무, 증명서, 품질문서, 업무일지, 출장복명서
- 최종 승인 시 `APPROVED_FINAL` + 결재란 **최종 PDF** 생성
- 반려 시 재상신 (Rev 자동 증가)
- 대시보드 **일괄 결재**(체크박스 다중 승인)

### 2. 일정관리 (캘린더)
- FullCalendar 기반 월/주/일 + 목록 뷰
- 일정 유형: 휴가, 전체일정, 측정팀1~5
- **휴가 결재 승인 → 캘린더에 자동 등록**, 반려 → 자동 취소
- 유형별 색상 구분 + 범례 필터

### 3. 업무일지 / 출장복명서
- 동적 행 추가/삭제 (JS)
- **업무일지**: 평일 전원(휴가 제외) · 주말 근무자만 → 저장 후 결재선 확인·상신. 결재 **동일 지사 차장~대표** 직급순·동직급 병렬, 작성자 **작성완료**
- **캘린더 측정팀 일정**: 유형 **측정팀1~5** 선택 시 **출장자** 다중 선택 가능 (주말 근무·업무일지 판정에 사용)
- **출장복명서 상신**: `관리팀`, `측정팀`(및 `측정팀1`~`5` 등 접두사 일치) 활성 사용자가 자동 결재선
- 출장복명서: **출장 지역** 마스터 선택·추가, 세금계산서 자동 합계, 사업자등록증 첨부
- 결재 최종 완료 시 `APPROVED_FINAL` → 회계 청구 집계 대상
- 결재 완료 후 상세 보기에서 테이블 형태로 표시

### 4. 회계 (일월계표 · 미수금대장) — Phase 5
- **일월계표** (`/accounting/dashboard`): 출장복명서 청구액 vs 수금액 비교
  - 조회: 일별 / 월별 / **분기** / **연별**
- **미수금대장** (`/accounting/ledger`): 업체·지역별 전월이월 / 당기발생 / 당기수금 / 미수잔액
  - 행별 수금 등록, html2pdf.js PDF 다운로드
- 지역은 `regions` 테이블로 정규화 (기본: 원주·제천·단양)

### 5. 품질문서 관리 (NAS 연동)
- NAS 볼륨(`/volume1/품질문서/...`)을 읽기 전용 마운트하여 폴더 트리 탐색
- PDF 인라인 미리보기 / 기타 파일 다운로드
- **재개정 이력 관리**: 문서번호별 전체 리비전 이력 (Rev 0, 1, 2...) 조회
- **버전 비교**: 이력 테이블에서 특정 버전 PDF를 뷰어에 즉시 로드
- 재개정 상신 → 결재 → 승인 시 아카이빙 자동 저장

### 6. 부가 기능
- **실시간 알림 (인페이지 팝업)**: 페이지 이동 없이 상단 종모양 아이콘을 클릭하여 알림 확인 및 바로가기
  - **알림 발생 조건**: 결재 상신(해당 결재자), 결재 승인/반려(상신자 및 다음 결재자), 쪽지 수신, **공지사항 등록**, **부재 자동 대결 지정**
- 게시판 (공지사항 등록 시 전 직원 알림 발송)
- 쪽지 (1:1 메시지, 발송 시 수신자에게 알림)
- 완료 문서 검색 (문서번호/제목/상신자/날짜) — `/completed`
- **통합 검색** (`/search`): 결재문서·게시판·첨부파일 한 번에 검색 (헤더 검색창)
- **조직도** (`/org`): 부서별 인원·쪽지 보내기 (상단 메뉴 **조직도**)
- **내 정보** (`/me`): 이름·부서·직급(드롭다운)·부재 대결자 수정
- **시스템 관리** (`/admin/users`, `/admin/depts`, `/admin/grades`, `/admin/nav`): 사용자·부서·직급 마스터, **상단 메뉴 표시 ON/OFF**, CSV 일괄 등록 (관리자 전용)

### 7. Phase 6 — 인프라·보안·검색·대결·PDF (2026-05)

| 기능 | 요약 |
|------|------|
| **DB 추상화** | `DATABASE_URL`로 SQLite / PostgreSQL / MariaDB 전환 (`app/database.py`) |
| **세션 유휴 만료** | 기본 2시간 미활동 시 자동 로그아웃 (`SESSION_IDLE_SECONDS`) |
| **IP 허용 목록** | `ALLOWED_IPS` 설정 시 사외 IP 차단 (403) |
| **통합 검색** | `/search` — 문서 제목·본문, 게시글, 첨부파일명 (권한 필터 적용) |
| **부재 자동 대결** | 휴가(`schedules` LEAVE) 중 결재자 → `delegate_id` 대결자로 자동 배정 |
| **PDF 워터마크** | 완료·품질 PDF 열람/다운로드 시 열람자·시각 동적 워터마크 (원본 파일 불변) |

상세: [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md) Phase 6 절 · [docs/REFERENCE.md](docs/REFERENCE.md)

---

## 보안 및 관리
본 시스템은 내부망 전용으로 설계되었으며, 다음과 같은 보안 조치가 적용되어 있습니다.

### 1. 보안 강화 조치

| 구분 | 내용 |
|------|------|
| **세션 쿠키** | HttpOnly, SameSite(Lax), 서명 쿠키 (`itsdangerous`) |
| **유휴 만료 (Phase 6.1)** | `SESSION_IDLE_SECONDS`(기본 7200) 동안 요청 없으면 `/login?reason=session_expired` |
| **절대 만료** | `SESSION_ABSOLUTE_SECONDS`(기본 30일) 초과 시 재로그인 |
| **IP 제한 (Phase 6.1)** | `ALLOWED_IPS` — `127.0.0.1`, `192.168.10.*`, CIDR 지원. 비우면 제한 없음 |
| **리버스 프록시** | NAS 앞단 프록시 사용 시 `TRUST_PROXY=1` + `X-Forwarded-For` 반영 |
| **파일 업로드** | 품질문서: 실행 파일 차단, 허용 확장자만 |
| **Path Traversal** | NAS 경로 `..` 차단 (`quality_fs.py`) |
| **PDF 워터마크 (Phase 6.4)** | 완료 PDF·품질 PDF 스트림 응답 시에만 합성, `data/final/` 원본 미변경 |
| **비밀 정보** | `.env`로 `APP_SECRET`, DB URL, 관리자 PW 분리 (Git 제외) |

### 2. 비밀번호·환경 파일
- **`.env`**: 프로젝트 루트에 `.env.example`을 복사해 사용 (`docker-compose`가 변수 전달)
- **Git**: `.env`는 절대 커밋하지 마십시오

---

## Synology NAS 설치 (Docker)

### 사전 조건
- DSM **Container Manager**(Docker) 패키지 설치
- 프로젝트 폴더를 NAS에 둠 (예: `/volume1/docker/approval_mvp`)

### 최초 설치 — SSH (권장)

DSM **제어판 → 터미널 및 SNMP**에서 SSH를 켠 뒤:

```bash
cd /volume1/docker/approval_mvp
docker compose up -d --build
```

브라우저: `http://NAS_IP:8080`

### 최초 설치 — Container Manager (GUI)

1. Container Manager → **프로젝트** → 생성  
2. 경로: `/volume1/docker/approval_mvp` 의 `docker-compose.yml` 선택  
3. **빌드** 후 **시작**

### 업데이트 / 재시작

프로젝트 폴더에서 실행합니다 (`cd /volume1/docker/approval_mvp`).

| 변경 내용 | 권장 명령 |
|-----------|-----------|
| `app/templates/`, `app/static/` 만 수정 | `docker compose restart approval` + 브라우저 **Ctrl+F5** |
| `app/main.py` 수정 (라우트·DB·PDF 등) | `docker compose restart approval` (볼륨 마운트면 재빌드 불필요) |
| `requirements.txt` / `Dockerfile` 수정 | **`docker compose build`** 후 `up -d` (Phase 6: `python-dotenv`, `psycopg`, `pymysql` 추가됨) |
| `.env`만 수정 (`DATABASE_URL`, `ALLOWED_IPS` 등) | `docker compose up -d` (재빌드 불필요) |
| 전체 재배포 | 아래 **완전 재기동** 참고 |

> **Phase 6 최초 반영 후**에는 의존성 설치를 위해 **한 번 `docker compose build`** 하는 것을 권장합니다.

**가벼운 재시작** (컨테이너만 다시 띄움, 데이터 유지):

```bash
docker compose restart approval
```

**완전 재기동** (이미지 다시 빌드 + 기동):

```bash
docker compose down
docker compose up -d --build
```

기동 시 `migrate_schema()`가 신규 테이블·컬럼을 자동 추가합니다 (`regions`, `collections`, `approvers.original_approver_id` 등).

**정상 기동 확인** — 로그 예시:

```text
INFO:     Application startup complete.
[startup] database dialect=sqlite
[migrate] schema migration completed (sqlite)
```

---

## 환경 변수 (docker-compose.yml)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `TZ` | `Asia/Seoul` | 시간대 (휴가·워터마크 시각) |
| `APP_SECRET` | (필수 변경) | 세션 서명 키 |
| `APP_ADMIN_ID` | `admin` | 최초 관리자 ID |
| `APP_ADMIN_PW` | — | 최초 관리자 PW |
| `APP_DATA_DIR` | `/data` (컨테이너) | DB·업로드·final PDF 경로 |
| `QUALITY_NAS_ROOT` | `/nas_quality` | NAS 품질문서 마운트 |
| `DATABASE_URL` | *(비움 → SQLite)* | DB 연결 문자열 (아래 예시) |
| `SESSION_IDLE_SECONDS` | `7200` | 유휴 세션 만료(초), 2시간 |
| `SESSION_ABSOLUTE_SECONDS` | `2592000` | 쿠키 최대 수명(초), 30일 |
| `ALLOWED_IPS` | *(비움 → 제한 없음)* | 허용 IP, 콤마 구분 |
| `TRUST_PROXY` | — | `1`이면 `X-Forwarded-For` 사용 |

**`.env` 예시** (프로젝트 루트 — `.env.example` 참고):

```env
APP_SECRET=여기에-충분히-긴-랜덤-문자열
APP_ADMIN_ID=admin
APP_ADMIN_PW=운영용-강한-비밀번호

# SQLite (기본, DATABASE_URL 비우면 data/app.db)
# DATABASE_URL=sqlite:////data/app.db

# PostgreSQL 예시
# DATABASE_URL=postgresql+psycopg://user:pass@db-host:5432/approval

# MariaDB 예시
# DATABASE_URL=mysql+pymysql://user:pass@db-host:3306/approval?charset=utf8mb4

# 사내망만 허용 (선택)
# ALLOWED_IPS=127.0.0.1,192.168.10.*,10.0.0.0/8
# TRUST_PROXY=1

SESSION_IDLE_SECONDS=7200
```

---

## 데이터 디렉터리 (./data)

```
data/
  app.db               ← SQLite 데이터베이스
  uploads/             ← 문서별 첨부파일 (doc_id별 하위폴더)
  final/               ← 최종 승인 PDF
  trash/               ← 소프트 삭제 파일
  quality_archive/     ← 품질문서 아카이빙 (doc_no별 하위폴더)
    QP-01-03/
      QP-01-03_Rev1_20260514.pdf
      QP-01-03_Rev2_20260514.hwp
```

---

## 사용 순서 (업무 흐름)

```
1. 관리자 로그인 → 상단 [관리] → 사용자 / 직급 탭에서 등록
2. 사용자 로그인 (첫 로그인 시 비밀번호 변경 강제)
3. [문서] → [새 문서] → 문서유형 선택 → 작성 → 결재선 지정 → 상신
4. 결재자: [문서] 목록에서 문서 열람 → 승인 또는 반려
5. 최종 승인 → [완료문서]에서 최종 PDF 확인/다운로드
```

### 결재 모드
| 모드 | 동작 |
|------|------|
| **순차** | 1번 결재자 승인 → 2번에게 넘어감 → ... → 전원 승인 시 완료 |
| **병렬** | 전 결재자 동시 결재 가능 → 전원 승인 시 완료 |

### 대결·부재 자동 위임 (Phase 6.3)
1. **내정보** (`/me`)에서 **대결자**(`users.delegate_id`) 지정 (선택)
2. 결재자가 **오늘 휴가**이면 (`schedules`: `LEAVE`, `ACTIVE`, 기간 내) 상신·다음 차례 시 **대결자에게 자동 배정**
3. **대결자를 지정하지 않으면** 원 결재자가 그대로 결재해야 함 (자동 승인·건너뛰기 없음)
4. 대결자에게 `[대결지정] OOO님의 부재로 …` 알림, 결재란에 `(원결재자 대결)` 표시
5. 휴가 일정: 휴가 결재 승인 시 자동 생성되거나, 일정 화면에서 `LEAVE` 유형 등록

### 문서 유형별 특이사항
| 유형 | 특이사항 |
|------|----------|
| 휴가신청 | 승인 시 캘린더에 자동 등록 |
| 업무일지 | **평일** 전원(휴가·제외 직급 제외) · **주말** 근무자만. 결재 **동일 지사 차장~대표** (`WORK_LOG_MIN/MAX_APPROVER_GRADE`). 상신자 지사 (`WORK_LOG-{WJ\|JC}-…`) |
| 출장복명서 | **관리·측정** 부서만 작성(접두사 일치, `관리팀`·`측정팀` 포함). 결재선 자동(관리·측정). **동일 지사** 회계 반영 |
| 품질문서 | 문서번호 지정 + Rev 관리 + NAS 라이브러리 연동 (**지사별 NAS**) |
| 회계 | [일월계표] 청구/수금 비교 · [미수금대장] 미수 관리·수금 등록 (**지사별**) |
| (공통) | 휴가·지출·연장·증명·일반결재 등 **모든 결재 문서**는 상신자 `users.branch_id` 기준으로 원주/제천 **분리 저장** |

---

## 시스템 관리 (관리자)

상단 메뉴 **관리** → **사용자** / **부서** / **직급** / **메뉴** 탭.  
`/admin` 접속 시 사용자 관리(`/admin/users`)로 이동합니다.

| 화면 | URL | 기능 |
|------|-----|------|
| 사용자 | `/admin/users` | 계정 추가·수정, **부서·직급은 드롭다운 선택만** (수기 입력 없음), CSV 일괄 등록, PW 초기화, 비활성화 |
| 부서 | `/admin/depts` | 부서명 추가, ▲▼ 순서, 비활성화·복구. **부서 추가는 여기서만** |
| 직급 | `/admin/grades` | 직급명 추가, ▲▼ 순서(위=높은 직급·결재는 아래 직급부터), 비활성화·복구. **직급 추가는 여기서만** |
| 메뉴 | `/admin/nav` | 상단 탭(검색·문서·회계·게시판 등) **표시/숨김**. 일반 사용자는 숨긴 메뉴·URL 접근 불가. **관리자는 항상 전체 표시** |

설정은 DB `app_settings` (`nav_visibility`)에 저장. 구현: `app/nav_settings.py`.

**부서·직급 사용 흐름**

1. **부서**·**직급** 탭에서 항목 등록 및 ▲▼로 순서 정리 (직급: 목록 위쪽일수록 높은 직급)
2. **사용자** 또는 본인 **내 정보**(`/me`)에서 드롭다운으로만 선택
3. CSV 등록 시 `dept`·`grade` 컬럼은 **부서/직급 관리에 등록된 이름과 정확히 일치**해야 반영 (미등록 시 빈 값)

서버 기동 시 기존 사용자의 부서 문자열이 `departments`에 없으면 **자동 시드**됩니다.

### 사용자 CSV 일괄 등록

**관리 → 사용자 → CSV 일괄 등록**에서 `.csv` 파일 업로드.

**1행 헤더 (필수, 순서 고정):**

```text
username,name,dept,grade,is_admin
```

| 컬럼 | 필수 | 설명 | 예시 |
|------|------|------|------|
| `username` | ○ | 로그인 ID (중복 시 해당 행 건너뜀) | `honggd` |
| `name` | ○ | 표시 이름 | `홍길동` |
| `dept` | — | 「부서」탭에 등록된 부서명과 일치 (미등록 시 빈 값) | `관리팀` |
| `grade` | — | 「직급」탭에 등록된 직급명과 일치 (미등록 시 빈 값) | `대리` |
| `is_admin` | — | 관리자 여부 (비우면 일반) | `0` 또는 `1` |

**예시 파일:**

```csv
username,name,dept,grade,is_admin
honggd,홍길동,경영지원팀,대리,0
kimys,김영수,환경사업부,과장,0
parkadmin,박관리,본사,,1
```

**규칙**

- 신규 `username`만 등록됩니다. 이미 있는 ID는 건너뜁니다.
- 초기 비밀번호: **`changeme123!`** (첫 로그인 시 변경 강제)
- `is_admin`: `1`, `Y`, `true`, `관리자` 등 → 관리자 / 그 외·비움 → 일반
- 엑셀 저장: **다른 이름으로 저장 → CSV UTF-8(쉼표로 분리)(*.csv)**
- 이름·부서에 쉼표가 있으면 셀을 큰따옴표로 감쌉니다. 예: `"영동,본사"`

### 관리 API (구현됨)

| 메서드 | URL | 기능 |
|--------|-----|------|
| POST | `/admin/users/add` | 사용자 추가 |
| POST | `/admin/users/import_csv` | CSV 일괄 등록 |
| POST | `/admin/users/reset_pw` | 비밀번호 `changeme123!` 초기화 |
| POST | `/admin/users/{id}/delete` | 계정 비활성화 |
| GET/POST | `/admin/users/{id}/edit` | 사용자 수정 |
| POST | `/admin/depts/add` | 부서 추가 |
| POST | `/admin/depts/{id}/move-up`, `move-down` | 부서 표시 순서 |
| POST | `/admin/depts/{id}/delete`, `restore` | 부서 비활성화·복구 |
| POST | `/admin/grades/add` | 직급 추가 |
| POST | `/admin/grades/{id}/move-up`, `move-down` | 직급 순서 (결재 순서에 반영) |
| POST | `/admin/grades/{id}/delete`, `restore` | 직급 비활성화·복구 |
| GET | `/admin/nav` | 상단 메뉴 표시 설정 화면 |
| POST | `/admin/nav/save` | 메뉴 표시 ON/OFF 저장 |
| GET/POST | `/me` | 내 정보 조회·저장 (부서·직급 드롭다운) |

처리 후 목록 화면에 안내 메시지(`?flash=`)가 표시됩니다.

### 출장복명서 결재 부서 (환경 변수)

`.env` (선택):

```env
# 콤마 구분. 부서명이 아래 문자열과 같거나 시작하면 결재 대상 (기본: 관리팀,측정팀)
TRIP_REPORT_APPROVAL_DEPTS=관리팀,측정팀
```

`측정팀1`~`측정팀5`는 `측정팀` 접두사로 자동 포함됩니다.

---

## UI (공통 디자인)

| 구분 | 내용 |
|------|------|
| 레이아웃 | `base.html` + `app/static/style.css` (인라인 CSS 제거) |
| 폰트 | Pretendard Variable (CDN) |
| 헤더 | 최대 1440px, 메뉴 **한 줄** + SVG 아이콘 + 현재 경로 **active** |
| 본문 | `container` 최대 1200px |
| 관리 | 통계 카드, 탭(사용자/부서/직급/**메뉴**), CSV 컬럼 표·예시 3행·엑셀 저장 안내 |
| 반응형 | **반응형 웹**(별도 모바일 앱 아님). PC 우선 UI, 스마트폰 브라우저에서도 사용 가능. 아래 표 참고 |

### 반응형·모바일 (브레이크포인트)

| 너비 | 동작 |
|------|------|
| **> 1280px** | 상단 메뉴 **한 줄**(필요 시 줄바꿈), 검색창·탭 항상 표시 |
| **≤ 1280px** | **햄버거(☰)** 메뉴. 펼치면 탭 **가로 한 줄 + 좌우 스크롤**(세로 쌓임 없음). 검색창은 헤더 아래 한 줄 |
| **≤ 768px** | 본문·카드 여백 축소, `.grid` 1열, 관리 화면 2열 그리드 → 1열 |
| **≤ 480px** | 알림 팝업 너비 조정 |

- `viewport` 메타 태그 적용 (`width=device-width`)
- 넓은 표(대시보드·회계·업무일지 등)는 `.table-responsive` **가로 스크롤**
- 캘린더·품질문서 라이브러리는 768px 이하에서 레이아웃 전환
- **한계**: 복잡한 문서 작성·넓은 회계 표는 PC가 더 편함. 결재 확인·알림·메뉴 이동은 모바일에서도 무난

관리자 **메뉴** 탭에서 끈 상단 탭은 일반 사용자에게만 숨김(관리자·`/admin`·`/api` 등은 항상 접근 가능).

### 상단 메뉴 URL

| 메뉴 | URL |
|------|-----|
| 통합 검색 | `/search` (헤더 검색창 동일) |
| 문서 | `/dashboard` |
| 완료 | `/completed` |
| 일월계표 | `/accounting/dashboard` |
| 미수금 | `/accounting/ledger` |
| 게시판 | `/boards` |
| 쪽지 | `/messages` |
| 품질 | `/quality/library` |
| 일정 | `/calendar` |
| 근무표 | `/work-schedule` |
| 휴가 | `/leave/status` |
| 조직도 | `/org` |
| 내정보 | `/me` |
| 관리 | `/admin/users` (관리자만) |

> 관리자가 **메뉴** 탭에서 끈 항목은 일반 사용자 헤더·직접 URL에서 숨김. 관리자 계정은 전체 표시.

---

## 결재 상태·문서 유형 (요약)

| 상태 코드 | 표시 | 비고 |
|-----------|------|------|
| `DRAFT` | 작성중 | |
| `IN_REVIEW` | 결재중 | 상신 후 |
| `APPROVED_FINAL` | 완료 | 회계·완료함 기준 |
| `REJECTED` | 반려 | |

| doc_type | 한글 |
|----------|------|
| `GENERAL` | 일반 기안 |
| `LEAVE` | 휴가 (승인→캘린더) |
| `TRIP_REPORT` | 출장복명서 (회계, 관리팀·측정팀 자동 결재) |
| `WORK_LOG` | 업무일지 (직급순·동직급 병렬) |
| `QUALITY` | 품질문서 |
| `EXPENSE` / `OVERTIME` / `CERTIFICATE` | 지출·연장·증명서 |

자세한 라우트·API·DB 목록: [docs/REFERENCE.md](docs/REFERENCE.md)

### 결재선·직급 규칙 (요약)

| 문서 유형 | 결재선 지정 | 결재 진행 |
|-----------|-------------|-----------|
| 일반·휴가·지출 등 | 체크박스로 결재자 선택 | **순차**: 직급 낮은 순 · **병렬**: 전원 동시 |
| 업무일지 | 자동 (동일 지사 **차장~대표**) | 직급 낮은 순, **동직급 병렬**. **작성자 = 작성완료** |
| 출장복명서 | 자동 (관리팀·측정팀) | 직급 낮은 순 순차 |

- 직급 순서: **시스템 관리 → 직급** 목록에서 ▲▼ 조정 (위쪽 = 높은 직급)
- DB `grades.level` 컬럼에 순서 저장 (`sort_order`로 매핑)
- 문서 `mode`: `SEQUENTIAL`, `PARALLEL`, 업무일지는 `GRADE_TIER`

---

## 회계 모듈 사용법

### 일월계표 (`/accounting/dashboard`)

| 조회 | 쿼리 예 | 설명 |
|------|---------|------|
| 일별 | `?mode=day&ref=2026-05-19` | 당일 청구·수금 요약 |
| 월별 | `?mode=month&ref=2026-05` | 월 내 일별 테이블 |
| 분기 | `?mode=quarter&ref=2026-Q2` | 분기 월별 테이블 |
| 연별 | `?mode=year&ref=2026` | 연간 월별 테이블 |

- **청구**: 최종 승인 출장복명서 라인 합계 (`외상+현금`, `line_date`)
- **수금**: `collections` 테이블 (`collection_date`)

### 미수금대장 (`/accounting/ledger`)

- 쿼리: `month`(YYYY-MM), `region_id`, `company`(업체명 부분 검색)
- 컬럼: 전월이월 · 당기발생 · 당기수금 · 미수잔액
- 행별 **수금 등록** → `POST /api/collections` (업체명·지역·금액·수금일)
- **PDF**: html2pdf.js (브라우저)

### 지역 추가

- 출장복명서 작성 화면 모달 또는 `POST /api/regions` (`{"name":"지역명"}`)
- 수금 시 `region_name`은 **regions에 등록된 이름**과 일치해야 함

---

## 통합 검색 (`/search`) — Phase 6.2

1. 로그인 후 **헤더 중앙 검색창**에 키워드 입력 (2자 이상) → Enter
2. 결과 페이지에서 탭: **전체 / 결재문서 / 게시판 / 첨부파일**
3. **결재문서·첨부**는 본인이 열람 권한 있는 건만 표시 (작성자·결재자·대결자·관리자)
4. **게시판**은 제목·본문 검색, 게시판명·작성자 메타 표시

---

## 품질문서 라이브러리 사용법

1. 상단 메뉴 **[품질문서]** 클릭
2. **좌측 트리**: NAS 폴더 구조 탐색, 파일 클릭 시 우측에 PDF 미리보기
3. **검색바**: 문서번호/제목 입력 → 자동완성 드롭다운 → 클릭 시 이력 로드
4. **재개정 이력 테이블**: 해당 문서의 모든 버전 표시
   - [PDF 보기]: 해당 버전 PDF를 상단 뷰어에 로드 (버전 간 비교 가능)
   - [원본↓]: 상신 시 첨부한 원본 파일(hwp, xls 등) 다운로드
   - [결재]: 해당 리비전의 결재 문서로 이동
5. **[재개정 상신]** 버튼: 새 리비전 파일 업로드 → 결재선 지정 → 상신
6. 최종 승인 시: 자동으로 아카이빙 + 이력 테이블 최상단에 새 버전 추가

**PDF 보안 (Phase 6.4):** 라이브러리·리비전 PDF **보기/다운로드** 시 `열람자: {이름} / 인쇄일시: {KST} / 무단배포 금지` 대각선 워터마크가 **응답 스트림에만** 적용됩니다. NAS·`data/final/` 원본 파일은 수정되지 않습니다.

---

## PDF 워터마크 적용 경로 (Phase 6.4)

| URL | 설명 |
|-----|------|
| `GET /doc/{id}/pdf` | 완료 문서 최종 PDF 다운로드 |
| `GET /preview/history/{id}` | 결재 이력 PDF 미리보기 |
| `GET /file/history/{id}` | 결재 이력 PDF 다운로드 |
| `GET /quality/revision/pdf?qd_id=` | 품질 리비전 PDF |
| `GET /quality/file/view?path=` | NAS PDF 인라인 (PDF만) |
| `GET /quality/file/download?path=` | NAS PDF 다운로드 |

**미적용:** 작성 중 원본 첨부 (`/preview/original`, `/file/original`) — 편집·검토용

---

## Phase 7 — 멀티 지사 (원주·제천)

### 요약

| 구분 | 동작 |
|------|------|
| **지사** | `branches` 테이블: 원주본사(`WJ`), 제천지사(`JC`). 사용자·문서·품질문서에 `branch_id` |
| **결재 문서 등록** | 업무일지·출장복명서·휴가·일반결재 등 **전 유형** — 상신자 **소속 지사**에 저장 (제천 직원 → JC, 원주 직원 → WJ) |
| **문서·대시보드 조회** | **한 화면에 원주+제천 통합 목록 없음**. 아래 「조회 권한」 참고 |
| **결재 후보** | 동일 지사 전원 + **「대표」 직급 및 그보다 높은 직급**(sort_order, `CROSS_BRANCH_REP_GRADE_NAME`) — **전 지사** 후보 |
| **게시판** | 지사 구분 없이 **통합** |
| **회계** | 일월계표·미수금·수금·지역 마스터 — **지사별**. 관리자·조회 전환 권한자는 `?branch_id=` 또는 헤더 조회 지사 |
| **조직도** | **전 지사 통합** — 지사별 섹션 → 부서별 카드 |
| **문서번호** | `{유형}-{지사코드}-{YYMM}-{순번}` 예: `WORK_LOG-JC-2605-003` |
| **품질 NAS** | `QUALITY_NAS_ROOT_WONJU`, `QUALITY_NAS_ROOT_JECHEON` (볼륨 분리) |

관리자: **시스템 관리 → 사용자**에서 지사 지정. CSV 컬럼 `branch` (`WJ` / `JC` / 지사명).

### 조회 권한 (자주 묻는 내용)

| 역할 | 보이는 문서 |
|------|-------------|
| **일반 직원** | **자기 지사** 문서만 (대시보드·문서 목록·검색의 문서 영역) |
| **일반 직원 (예외)** | 결재선·대결에 **본인이 포함된 타지사 문서**는 해당 건만 추가 노출 |
| **관리자** (`is_admin`) | 헤더 **「조회」**로 원주 ↔ 제천 **전환** (쿠키 `view_branch_id`). 통합 목록 없음 |
| **원주본사 대표 및 그 위** | `is_headquarters`(WJ) 소속이면서 「대표」 이상 직급만 조회 전환. **제천 대표는 전환 불가** (제천 문서만 조회) |

> 관리자·원주 대표도 **한 화면에 전 지사 합치지 않음**. 타지사는 헤더에서 지사를 바꿉니다.

### 작성 규칙 (지사와 별개)

| 유형 | 규칙 |
|------|------|
| **업무일지** | **평일** 전원(`WORK_LOG_EXEMPT_GRADES`·당일 휴가 제외) · **주말** 출장 일정·주말근무·근무표 근무자만. 결재 **동일 지사 차장~대표** (`GRADE_TIER`) |
| **출장복명서** | **관리·측정** 부서만 (`TRIP_REPORT_WRITER_DEPTS` 기본 `관리,측정`). **본인 지사** |
| **근무표** | `/work-schedule` — **이사 이상 제외**, 주간 **조기+연장**·**주말** 합계(수당), 휴무·휴가·공휴(기본 8.5h 제외), 승인 휴가 자동 휴무. 월간 결재(TIMESHEET) |
| **휴가·연차 조회** | `/leave/status` — **1/1~12/31** 지사별 집계. **외출** 포함(8.5h=연차1일, 30분 단위 환산) |
| **외출** | 휴가신청 종류 **외출** — 30분~8.5h 선택, 연차사용에 자동 환산 (전일 휴가 일정 미생성) |
| **그 외 결재** | 지사 제한 없이 유형별 폼·결재선 규칙 적용, 저장은 **상신자 지사** |

구현: `app/branch_scope.py`, `app/doc_requirements.py`, `app/nav_settings.py` (메뉴 표시).

상세: [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md) Phase 7 · [docs/REFERENCE.md](docs/REFERENCE.md) · [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## 문제 해결

### 로그 보는 법

NAS **SSH** 또는 아래 **Container Manager** 로그 탭에서 확인합니다.

```bash
cd /volume1/docker/approval_mvp
```

| 목적 | 명령 |
|------|------|
| **실시간 로그** (오류 나올 때까지 따라보기, 종료: Ctrl+C) | `docker compose logs -f approval` |
| **최근 50줄만** | `docker compose logs --tail=50 approval` |
| **컨테이너 이름으로** | `docker logs -f approval_mvp` |

**컨테이너가 안 뜰 때** 순서:

```bash
docker compose ps -a          # STATUS가 Exited / Restarting 인지 확인
docker compose logs --tail=80 approval   # 맨 아래 Traceback / SyntaxError 확인
```

자주 보는 메시지:

| 로그 | 의미 |
|------|------|
| `Application startup complete` | 앱 정상 기동 |
| `SyntaxError` / `ModuleNotFoundError` | `main.py` 문법 오류 또는 패키지 미설치 → 코드 수정 후 **재빌드** |
| `[migrate] schema migration completed (sqlite)` | DB 스키마 보강 완료 (dialect 표시) |
| `[startup] database dialect=postgresql` | PostgreSQL 등 외부 DB 연결 |
| `403` + IP 메시지 | `ALLOWED_IPS`에 현재 IP 없음 |
| 로그인 후 곧 튕김 | `SESSION_IDLE_SECONDS` 확인, 활동 시 쿠키 갱신됨 |
| `[seed] demo completed PDF sample` | 예시 완료 문서 시드 완료 (선택) |

**Synology Container Manager (GUI):**  
Container Manager → 컨테이너 **`approval_mvp`** 선택 → **세부 정보** → **로그** 탭.

### 컨테이너 상태 확인

```bash
docker compose ps -a
```

`approval_mvp` 의 `STATUS` 가 **Up** 이고 `PORTS` 가 `0.0.0.0:8080->8000/tcp` 이면 접속 가능합니다.

### 재시작 (문제 해결용)

```bash
cd /volume1/docker/approval_mvp
docker compose restart approval
docker compose logs --tail=30 approval
```

코드·의존성 변경 후에는 [업데이트 / 재시작](#업데이트--재시작) 절의 **완전 재기동**을 사용하세요.

### DB 초기화 (주의: 모든 데이터 삭제)

```bash
rm -f ./data/app.db
docker compose restart approval
```

### 포트 충돌
`docker-compose.yml`의 `ports`에서 `8080`을 다른 포트로 변경

---

## DB 마이그레이션 (`migrate_schema`)

컨테이너/앱 **기동 시 자동** 실행 (`app/database.py` → `run_schema_migration`). 기존 DB 데이터는 유지하고 컬럼만 추가합니다.

| 대상 | 보강 내용 |
|------|-----------|
| documents | doc_type, rev, 휴가/연장/증명서 필드, expense_total 등 |
| users | must_change_pw, is_admin, grade_id, **delegate_id** |
| approvers | **original_approver_id** (자동 대결 감사용, Phase 6.3) |
| attachments | uploader_id, filesize, created_at (+ 작성자 백필) |
| trip_reports | region_id |
| regions / collections | Phase 5 테이블·시드(원주·제천·단양) |
| 상태 정리 | `APPROVED` → `APPROVED_FINAL` |

- **SQLite**: `PRAGMA table_info` 기반 ADD COLUMN  
- **PostgreSQL / MariaDB**: `DATABASE_URL` 설정 시 `inspect` 기반 동일 로직 (dialect별 DDL 분기)

로그 예: `[migrate] schema migration completed (sqlite)`

---

## 개발·점검 스크립트 (`scripts/`)

| 파일 | 용도 |
|------|------|
| `check_db.py` | DB 연결·admin 계정 확인 |
| `check_completed.py` | 완료 문서 페이지 HTTP 점검 |
| `test_pages.py` | 주요 페이지 스모크 테스트 |
| `diag_500.py` | 500 오류 진단 |

---

## 관련 문서

| 문서 | 설명 |
|------|------|
| [docs/REFERENCE.md](docs/REFERENCE.md) | **전체 라우트·상태코드·DB 모델·관리 API 현황** (상세) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 구조, 스키마, 작동 로직·흐름도 |
| [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md) | Phase 1~6 개발 계획 및 진행 기록 |
| `.env.example` | 환경 변수 템플릿 (DB·세션·IP) |
| [FIXES_SUMMARY.md](FIXES_SUMMARY.md) | 버그 수정 및 기능 추가 전체 이력 |
