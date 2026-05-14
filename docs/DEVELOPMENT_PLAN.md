# 결재 시스템 확장 — 개발 계획 및 진행 기록

> 일정관리 / 업무일지·출장복명서 / 품질문서(NAS 연동) 확장을 **Phase 1~4**로 나누어 구현.  
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

## 기타 수정사항

| 날짜 | 내용 |
|------|------|
| 2026-05-13 | `base.html` 네비에서 직급 링크 제거 (사용자 관리에서 접근 가능) |
| 2026-05-14 | `README.md` 전면 개편, `docs/ARCHITECTURE.md` 신규 작성, `FIXES_SUMMARY.md` 갱신 |

---

## 참고 문서

| 문서 | 설명 |
|------|------|
| `README.md` | 설치, 사용법, 환경변수, 폴더 구조 |
| `docs/ARCHITECTURE.md` | 파일 구조, DB 스키마, 라우트 맵, 작동 로직 상세 |
| `FIXES_SUMMARY.md` | 초기 버그 수정 + Phase 1~4 전체 변경 이력 |
