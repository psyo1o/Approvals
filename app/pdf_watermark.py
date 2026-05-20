"""PDF 열람·다운로드 시 동적 보안 워터마크 (Phase 6.4)."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from io import BytesIO
from typing import List, Optional
from zoneinfo import ZoneInfo

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

KST = ZoneInfo("Asia/Seoul")
_FONT_REGISTERED = False


def nanum_font_path() -> str:
    candidates = (
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicRegular.ttf",
        "/usr/share/fonts/opentype/nanum/NanumGothic.otf",
    )
    for path in candidates:
        if os.path.isfile(path):
            return path
    return ""


def _ensure_korean_font() -> str:
    global _FONT_REGISTERED
    font_path = nanum_font_path()
    if font_path and not _FONT_REGISTERED:
        pdfmetrics.registerFont(TTFont("PdfWatermarkKorean", font_path))
        _FONT_REGISTERED = True
        return "PdfWatermarkKorean"
    if _FONT_REGISTERED:
        return "PdfWatermarkKorean"
    return "Helvetica"


def format_viewed_at_kst(viewed_at: datetime) -> str:
    dt = viewed_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M")


def build_watermark_lines(viewer_name: str, viewed_at: Optional[datetime] = None) -> List[str]:
    """한 줄에 몰아 넣지 않고 3줄로 분리해 겹침·가독성 문제를 줄임."""
    name = (viewer_name or "알 수 없음").strip()
    ts = format_viewed_at_kst(viewed_at or datetime.now(timezone.utc))
    return [
        f"열람자: {name}",
        f"인쇄일시: {ts}",
        "무단배포 금지",
    ]


def build_watermark_line(viewer_name: str, viewed_at: Optional[datetime] = None) -> str:
    """하위 호환."""
    return " · ".join(build_watermark_lines(viewer_name, viewed_at))


def _text_width(text: str, font_name: str, font_size: float) -> float:
    try:
        return float(pdfmetrics.stringWidth(text, font_name, font_size))
    except Exception:
        return len(text) * font_size * 0.5


def _draw_lines_block(
    c: canvas.Canvas,
    cx: float,
    cy: float,
    lines: List[str],
    font_name: str,
    font_size: float,
    leading: float,
) -> None:
    top_y = cy + (len(lines) - 1) * leading * 0.5
    for i, line in enumerate(lines):
        c.drawCentredString(cx, top_y - i * leading, line)


def _make_watermark_page(width: float, height: float, lines: List[str]) -> bytes:
    font_name = _ensure_korean_font()
    font_size = max(10.0, min(13.0, min(width, height) / 55.0))
    leading = font_size * 1.45
    block_w = max(_text_width(line, font_name, font_size) for line in lines)
    block_h = leading * (len(lines) - 1) + font_size

    # 블록 간격: 텍스트 폭·높이보다 충분히 크게 (겹침 방지)
    gap_x = max(block_w * 1.35, 280.0)
    gap_y = max(block_h * 2.2, 120.0)

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    c.saveState()
    c.setFillColor(Color(0.4, 0.4, 0.4, alpha=1.0))
    c.setFont(font_name, font_size)
    c.translate(width * 0.5, height * 0.5)
    c.rotate(45)

    # 페이지 대각선 길이 기준으로 필요한 반복 수만 계산 (최대 3×3)
    diag = (width * width + height * height) ** 0.5
    cols = max(1, min(3, int(diag / gap_x) + 1))
    rows = max(1, min(3, int(diag / gap_y) + 1))
    x0 = -(cols - 1) * gap_x * 0.5
    y0 = -(rows - 1) * gap_y * 0.5

    for row in range(rows):
        for col in range(cols):
            # 가운데 블록을 조금 더 진하게, 나머지는 연하게
            is_center = rows == 1 or (row == rows // 2 and col == cols // 2)
            c.setFillAlpha(0.20 if is_center else 0.11)
            x = x0 + col * gap_x
            y = y0 + row * gap_y
            _draw_lines_block(c, x, y, lines, font_name, font_size, leading)

    c.restoreState()
    c.showPage()
    c.save()
    return buf.getvalue()


def apply_viewer_watermark(
    pdf_bytes: bytes,
    viewer_name: str,
    viewed_at: Optional[datetime] = None,
) -> bytes:
    """원본 PDF 바이트에 워터마크를 합성해 반환 (디스크 파일은 변경하지 않음)."""
    lines = build_watermark_lines(viewer_name, viewed_at)
    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()
    if not reader.pages:
        return pdf_bytes
    for page in reader.pages:
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        wm_pdf = _make_watermark_page(w, h, lines)
        wm_page = PdfReader(BytesIO(wm_pdf)).pages[0]
        page.merge_page(wm_page)
        writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
