"""
Phase 4 — NAS 볼륨 품질문서 스캔 서비스
docker-compose에서 마운트된 /app/nas_external (읽기 전용)을 스캔하여
폴더 트리와 파일 목록을 반환한다.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

NAS_ROOT = os.environ.get("QUALITY_NAS_ROOT", "/app/nas_external")

VIEWABLE_EXTENSIONS = {".pdf"}
DOWNLOADABLE_EXTENSIONS = {
    ".pdf", ".hwp", ".hwpx",
    ".xls", ".xlsx", ".xlsm",
    ".doc", ".docx",
    ".ppt", ".pptx",
    ".jpg", ".jpeg", ".png", ".gif",
    ".zip", ".7z",
}


def _safe_resolve(base: str, rel: str) -> Optional[str]:
    """path traversal 방지 — base 안에 있는 경로만 허용"""
    try:
        base_p = Path(base).resolve()
        target = (base_p / rel).resolve()
        if str(target).startswith(str(base_p)):
            return str(target)
    except Exception:
        pass
    return None


def scan_tree(current: str = NAS_ROOT, *, _origin: str = "") -> list[dict]:
    """
    NAS 루트 아래 폴더 트리를 재귀 스캔하여 리스트로 반환.
    rel_path는 항상 최초 루트(_origin) 기준이므로 다운로드/뷰 URL에 그대로 사용 가능.
    """
    origin = _origin or current
    result = []
    cur_p = Path(current)
    origin_p = Path(origin)
    if not cur_p.is_dir():
        return result

    try:
        entries = sorted(cur_p.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return result

    for entry in entries:
        rel = str(entry.relative_to(origin_p))
        node: dict = {
            "name": entry.name,
            "rel_path": rel.replace("\\", "/"),
            "is_dir": entry.is_dir(),
            "ext": entry.suffix.lower() if entry.is_file() else "",
            "size": entry.stat().st_size if entry.is_file() else 0,
            "children": [],
        }
        if entry.is_dir():
            node["children"] = scan_tree(str(entry), _origin=origin)
        result.append(node)
    return result


def search_files(query: str, root: str = NAS_ROOT) -> list[dict]:
    """파일명·경로에 query가 포함된 파일만 플랫 리스트로 반환"""
    results = []
    q = query.lower()
    root_p = Path(root)
    if not root_p.is_dir():
        return results
    for p in root_p.rglob("*"):
        if p.is_file() and q in p.name.lower():
            results.append({
                "name": p.name,
                "rel_path": str(p.relative_to(root_p)).replace("\\", "/"),
                "ext": p.suffix.lower(),
                "size": p.stat().st_size,
            })
    return results


def resolve_file_path(rel_path: str, root: str = NAS_ROOT) -> Optional[str]:
    """상대 경로를 검증 후 절대 경로 반환 (traversal 차단)"""
    return _safe_resolve(root, rel_path)


def can_inline_view(ext: str) -> bool:
    return ext.lower() in VIEWABLE_EXTENSIONS


def can_download(ext: str) -> bool:
    return ext.lower() in DOWNLOADABLE_EXTENSIONS
