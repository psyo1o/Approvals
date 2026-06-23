"""
Phase 4 / 7 — NAS 볼륨 품질문서 스캔 (지사별 루트).
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

NAS_ROOT = os.environ.get("QUALITY_NAS_ROOT", "/app/nas_external")
NAS_ROOT_WONJU = os.environ.get("QUALITY_NAS_ROOT_WONJU", NAS_ROOT)
NAS_ROOT_JECHEON = os.environ.get("QUALITY_NAS_ROOT_JECHEON", NAS_ROOT)

DEFAULT_BRANCH_ID = 1
JECHEON_BRANCH_ID = 2

VIEWABLE_EXTENSIONS = {".pdf"}
DOWNLOADABLE_EXTENSIONS = {
    ".pdf", ".hwp", ".hwpx",
    ".xls", ".xlsx", ".xlsm",
    ".doc", ".docx",
    ".ppt", ".pptx",
    ".jpg", ".jpeg", ".png", ".gif",
    ".zip", ".7z",
}

# NAS/OS 숨김·시스템 파일 (품질문서 트리·검색에서 제외)
_HIDDEN_BASENAMES = frozenset(
    {"thumbs.db", "desktop.ini", ".ds_store", "icon\r", "icon"}
)


def _is_hidden_name(name: str) -> bool:
    """점(.) 시작, Synology @폴더, macOS ._ 리소스 등."""
    n = (name or "").strip()
    if not n:
        return True
    if n.startswith(".") or n.startswith("@") or n.startswith("._"):
        return True
    if n.lower() in _HIDDEN_BASENAMES:
        return True
    return False


def nas_root_for_branch(branch_id: Optional[int] = None) -> str:
    bid = int(branch_id) if branch_id is not None else DEFAULT_BRANCH_ID
    if bid == JECHEON_BRANCH_ID:
        return NAS_ROOT_JECHEON
    return NAS_ROOT_WONJU


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


def scan_tree(
    current: Optional[str] = None,
    *,
    branch_id: Optional[int] = None,
    _origin: str = "",
) -> list[dict]:
    root = current or nas_root_for_branch(branch_id)
    origin = _origin or root
    result = []
    cur_p = Path(root)
    origin_p = Path(origin)
    if not cur_p.is_dir():
        return result

    try:
        entries = sorted(cur_p.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return result

    for entry in entries:
        if _is_hidden_name(entry.name):
            continue
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
            node["children"] = scan_tree(str(entry), branch_id=branch_id, _origin=origin)
        result.append(node)
    return result


def search_files(query: str, *, branch_id: Optional[int] = None, root: Optional[str] = None) -> list[dict]:
    """파일명·경로에 query가 포함된 파일만 플랫 리스트로 반환"""
    root = root or nas_root_for_branch(branch_id)
    results = []
    q = query.lower()
    root_p = Path(root)
    if not root_p.is_dir():
        return results
    for p in root_p.rglob("*"):
        if any(_is_hidden_name(part) for part in p.parts):
            continue
        if p.is_file() and q in p.name.lower():
            results.append({
                "name": p.name,
                "rel_path": str(p.relative_to(root_p)).replace("\\", "/"),
                "ext": p.suffix.lower(),
                "size": p.stat().st_size,
            })
    return results


def resolve_file_path(rel_path: str, *, branch_id: Optional[int] = None, root: Optional[str] = None) -> Optional[str]:
    root = root or nas_root_for_branch(branch_id)
    return _safe_resolve(root, rel_path)


def can_inline_view(ext: str) -> bool:
    return ext.lower() in VIEWABLE_EXTENSIONS


def can_download(ext: str) -> bool:
    return ext.lower() in DOWNLOADABLE_EXTENSIONS
