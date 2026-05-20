# (주)영동환경이앤텍 — 전자결재 시스템

> Synology NAS Docker 기반 내부망 전용 전자결재 + 일정관리 + 품질문서 관리 시스템

---

## 한눈에 보기

| 항목 | 내용 |
|------|------|
| 백엔드 | Python 3.11 / FastAPI |
| 데이터베이스 | SQLite (SQLAlchemy ORM) |
| 프론트엔드 | Jinja2 템플릿 + Vanilla JS + 공통 CSS (`style.css`, Pretendard 폰트) |
| 배포 | Docker Compose → Synology NAS |
| 접속 주소 | `http://NAS_IP:8080` |
| 기본 관리자 | ID: `admin` / PW: `admin1234!` |

---

## 주요 기능

### 1. 전자결재
- 문서 작성 → 결재선 지정(순차/병렬) → 상신 → 승인/반려
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
  - **알림 발생 조건**: 결재 상신(해당 결재자), 결재 승인/반려(상신자 및 다음 결재자), 쪽지 수신, **공지사항 등록**
- 게시판 (공지사항 등록 시 전 직원 알림 발송)
- 쪽지 (1:1 메시지, 발송 시 수신자에게 알림)
- 완료 문서 검색 (문서번호/제목/상신자/날짜)
- **시스템 관리** (`/admin/users`, `/admin/grades`): 사용자·직급 관리, CSV 일괄 등록 (관리자 전용)

---

## 보안 및 관리
본 시스템은 내부망 전용으로 설계되었으며, 다음과 같은 보안 조치가 적용되어 있습니다.

### 1. 보안 강화 조치 (2026-05-14)
- **세션 보안**: HttpOnly, SameSite(Lax) 속성을 적용하여 쿠키 탈취 및 CSRF 공격을 방어합니다.
- **파일 업로드 제한**: 품질문서 개정 시 실행 파일(`.exe`, `.sh` 등) 업로드를 차단하고 허용된 문서 확장자만 허용합니다.
- **경로 조작 방어 (Path Traversal)**: NAS 볼륨 탐색 시 상위 디렉터리 접근을 원천 차단하는 검증 로직이 포함되어 있습니다.
- **비밀 정보 분리**: `docker-compose.yml`에서 비밀번호를 분리하여 `.env` 파일로 관리합니다.

### 2. 비밀번호 관리
- **환경 변수 파일(`.env`)**: `docker-compose.yml`과 같은 위치(NAS 프로젝트 폴더)에 생성하여 `APP_ADMIN_PW` 등을 관리하십시오.
- **GitHub 주의**: `.env` 파일은 절대 Git에 커밋하지 마십시오. (`.gitignore`에 포함되어 있음)

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
| `requirements.txt` / `Dockerfile` 수정 | `docker compose build approval --no-cache` 후 `docker compose up -d approval` |
| 전체 재배포 | 아래 **완전 재기동** 참고 |

**가벼운 재시작** (컨테이너만 다시 띄움, 데이터 유지):

```bash
docker compose restart approval
```

**완전 재기동** (이미지 다시 빌드 + 기동):

```bash
docker compose down
docker compose up -d --build
```

기동 시 `migrate_schema()`가 신규 테이블·컬럼을 자동 추가합니다 (`regions`, `collections`, `attachments.uploader_id` 등).

**정상 기동 확인** — 로그 마지막에 아래가 보이면 OK:

```text
INFO:     Application startup complete.
[migrate] schema migration completed successfully
```

---

## 환경 변수 (docker-compose.yml)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `TZ` | `Asia/Seoul` | 시간대 |
| `APP_SECRET` | `change-me-long-random` | 세션 암호화 키 (반드시 변경) |
| `APP_ADMIN_ID` | `admin` | 최초 관리자 ID |
| `APP_ADMIN_PW` | `admin1234!` | 최초 관리자 PW |
| `QUALITY_NAS_ROOT` | `/nas_quality` | 컨테이너 내 NAS 마운트 경로 |

`.env` 파일 예시 (프로젝트 루트, Git 제외):

```env
APP_SECRET=여기에-충분히-긴-랜덤-문자열
APP_ADMIN_ID=admin
APP_ADMIN_PW=운영용-강한-비밀번호
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

### 문서 유형별 특이사항
| 유형 | 특이사항 |
|------|----------|
| 휴가신청 | 승인 시 캘린더에 자동 등록 |
| 업무일지 | 행 단위 동적 입력 (팀명/업체명/내용/주행거리/수주번호) |
| 출장복명서 | 지역 선택·추가, 세금계산서 행 + 합계, 사업자등록증 첨부 → **APPROVED_FINAL** 시 회계 반영 |
| 품질문서 | 문서번호 지정 + Rev 관리 + NAS 라이브러리 연동 |
| 회계 | [일월계표] 청구/수금 비교 · [미수금대장] 미수 관리·수금 등록 |

---

## 시스템 관리 (관리자)

상단 메뉴 **관리** → **사용자** / **직급** 탭 (`/admin/users`, `/admin/grades`).  
`/admin` 접속 시 사용자 관리 화면으로 이동합니다.

| 화면 | 기능 |
|------|------|
| 사용자 | 계정 추가, 목록·수정·비밀번호 초기화·비활성화, **CSV 일괄 등록** |
| 직급 | 직급명 추가, 비활성화·복구 |

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
| `dept` | — | 부서 | `경영지원팀` |
| `grade` | — | 「직급」탭에 등록된 직급명과 일치 | `대리` |
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
| POST | `/admin/grades/add` | 직급 추가 |
| POST | `/admin/grades/{id}/delete` | 직급 비활성화 |
| POST | `/admin/grades/{id}/restore` | 직급 복구 |

처리 후 목록 화면에 안내 메시지(`?flash=`)가 표시됩니다.

---

## UI (공통 디자인)

| 구분 | 내용 |
|------|------|
| 레이아웃 | `base.html` + `app/static/style.css` (인라인 CSS 제거) |
| 폰트 | Pretendard Variable (CDN) |
| 헤더 | 최대 1440px, 메뉴 **한 줄** + SVG 아이콘 + 현재 경로 **active** |
| 본문 | `container` 최대 1200px |
| 관리 | 통계 카드, 탭(사용자/직급), CSV 컬럼 표·예시 3행·엑셀 저장 안내 |
| 반응형 | ≤1100px 메뉴 아이콘만, ≤768px 햄버거 |

### 상단 메뉴 URL

| 메뉴 | URL |
|------|-----|
| 문서 | `/dashboard` |
| 완료 | `/completed` |
| 일월계표 | `/accounting/dashboard` |
| 미수금 | `/accounting/ledger` |
| 게시판 | `/boards` |
| 쪽지 | `/messages` |
| 품질 | `/quality/library` |
| 일정 | `/calendar` |
| 조직도 | `/org` |
| 내정보 | `/me` |
| 관리 | `/admin/users` (관리자만) |

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
| `TRIP_REPORT` | 출장복명서 (회계) |
| `WORK_LOG` | 업무일지 |
| `QUALITY` | 품질문서 |
| `EXPENSE` / `OVERTIME` / `CERTIFICATE` | 지출·연장·증명서 |

자세한 라우트·API·DB 목록: [docs/REFERENCE.md](docs/REFERENCE.md)

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
| `migrate_schema completed successfully` | DB 스키마 보강 완료 |
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

컨테이너/앱 **기동 시 자동** 실행. 기존 `data/app.db` 데이터는 유지하고 컬럼만 추가합니다.

| 대상 | 보강 내용 |
|------|-----------|
| documents | doc_type, rev, 휴가/연장/증명서 필드, expense_total 등 |
| users | must_change_pw, is_admin, grade_id, delegate_id |
| attachments | **uploader_id**, filesize, created_at (+ 작성자 백필) |
| trip_reports | region_id |
| regions / collections | Phase 5 테이블·시드(원주·제천·단양) |
| 상태 정리 | `APPROVED` → `APPROVED_FINAL` |

로그: `[migrate] schema migration completed successfully`

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
| [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md) | Phase 1~5 개발 계획 및 진행 기록 |
| [FIXES_SUMMARY.md](FIXES_SUMMARY.md) | 버그 수정 및 기능 추가 전체 이력 |
