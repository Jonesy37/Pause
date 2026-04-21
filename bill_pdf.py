"""
bill_pdf.py — Render the bill section of solution.md to a PDF.

The bill is authored in a predictable subset of HTML-in-markdown:

    <h3 class="bill-title">...</h3>
    <h4 class="bill-section-heading">...</h4>
    <p class="lvl-0">...</p>
    <p class="lvl-1">...</p>
    <p class="lvl-2">...</p>

plus inline <span class="tip"><span class="tip-body">...</span></span>
citation pop-ups and ordinary <a href>...</a> links. For the PDF we
flatten tooltips to "visible text (source: <url>)" footnote-style, and
drop the outer <div class="bill"> wrapper entirely.

Pure-Python (fpdf2 + stdlib only) so the Render build stays lean — no
cairo/pango system dependencies.
"""

from __future__ import annotations

import re
from html import unescape
from io import BytesIO
from pathlib import Path

from fpdf import FPDF


# ----------------------------------------------------------------------
#  Parsing: pull the ordered list of (kind, text) blocks from solution.md
# ----------------------------------------------------------------------

# One "block" per heading or paragraph. Kind is the CSS class so the
# renderer can pick font size + left indent for each.
BLOCK_RE = re.compile(
    r'<(h3|h4|p)[^>]*class="([^"]+)"[^>]*>(.*?)</\1>',
    re.DOTALL | re.IGNORECASE,
)

# Strip HTML comments (the long editor-facing header at the top).
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _flatten_tooltip(match: re.Match) -> str:
    """
    <span class="tip">visible<span class="tip-body">
        <a href="URL">Description.</a>
    </span></span>
        -->
    "visible (source: URL)"
    """
    inner = match.group(1)
    # Grab the first href in the tip-body, if any.
    href_match = re.search(r'href="([^"]+)"', inner)
    # The visible label is everything before the nested tip-body span.
    body_split = re.split(
        r'<span\s+class="tip-body"[^>]*>', inner, maxsplit=1, flags=re.IGNORECASE
    )
    visible = body_split[0]
    visible = re.sub(r"<[^>]+>", "", visible).strip()
    if href_match:
        return f"{visible} [source: {href_match.group(1)}]"
    return visible


TIP_RE = re.compile(
    r'<span\s+class="tip"[^>]*>(.*?)</span>\s*</span>',
    re.DOTALL | re.IGNORECASE,
)
ANCHOR_RE = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE)


def _flatten_inline(html: str) -> str:
    """Resolve inline tags down to plain text that's safe for PDF output."""
    # Flatten .tip hover pop-ups to inline [source: URL] callouts.
    html = TIP_RE.sub(_flatten_tooltip, html)
    # Flatten ordinary anchors to 'label (URL)'.
    html = ANCHOR_RE.sub(lambda m: f"{re.sub(r'<[^>]+>', '', m.group(2))} ({m.group(1)})", html)
    # Drop any remaining tags (e.g. stray <span>, <em>, <strong>).
    html = re.sub(r"<[^>]+>", "", html)
    # Collapse whitespace introduced by the source file's indentation.
    html = re.sub(r"\s+", " ", html)
    return unescape(html).strip()


def parse_bill(md_path: Path) -> list[tuple[str, str]]:
    """Return an ordered list of (kind, text) pairs — kind is the CSS class."""
    raw = md_path.read_text(encoding="utf-8")
    raw = COMMENT_RE.sub("", raw)
    blocks: list[tuple[str, str]] = []
    for tag, cls, inner in BLOCK_RE.findall(raw):
        # Keep only the first class token (e.g. "bill-title" from
        # "bill-title extra-class") since that's what we key off.
        kind = cls.split()[0]
        blocks.append((kind, _flatten_inline(inner)))
    return blocks


# ----------------------------------------------------------------------
#  Rendering: walk the blocks and emit a PDF
# ----------------------------------------------------------------------

# Page layout constants. US Letter; 1-inch margins (72 pt).
PAGE_SIZE = "Letter"
MARGIN = 72 / 2.83464567  # fpdf2's default unit is mm — 1 in = 25.4 mm
# Actually: fpdf2 default is mm. 1" = 25.4 mm.
MARGIN_MM = 25.4

# Indent per "level" of legal numbering, in mm.
INDENT_MM = 9.0

# Font sizes (pt).
SIZE_TITLE = 14
SIZE_HEADING = 12
SIZE_BODY = 11


class BillPDF(FPDF):
    """FPDF subclass with a simple header + footer."""

    def footer(self):
        # Page number centered in the bottom margin.
        self.set_y(-15)
        self.set_font("Helvetica", "I", 9)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def render_bill_pdf(md_path: Path) -> bytes:
    """Return the bill as PDF bytes."""
    blocks = parse_bill(md_path)

    pdf = BillPDF(orientation="portrait", unit="mm", format=PAGE_SIZE)
    pdf.set_auto_page_break(auto=True, margin=25)
    pdf.set_margins(MARGIN_MM, MARGIN_MM, MARGIN_MM)
    pdf.add_page()

    content_width = pdf.w - MARGIN_MM * 2

    for kind, text in blocks:
        if not text:
            continue

        if kind == "bill-title":
            pdf.set_font("Helvetica", "B", SIZE_TITLE)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(2)
            pdf.multi_cell(content_width, 8, text, align="C")
            pdf.ln(4)

        elif kind == "bill-section-heading":
            # Keep headings with at least one line of body below them.
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", SIZE_HEADING)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(content_width, 6.5, text, align="C")
            pdf.ln(2)

        elif kind.startswith("lvl-"):
            try:
                level = int(kind.split("-")[1])
            except (IndexError, ValueError):
                level = 0
            indent = INDENT_MM * level
            pdf.set_font("Helvetica", "", SIZE_BODY)
            pdf.set_text_color(20, 20, 20)
            # Offset the left edge manually so wrapped lines also indent.
            pdf.set_x(MARGIN_MM + indent)
            pdf.multi_cell(content_width - indent, 5.5, text)
            pdf.ln(1.5)

        else:
            # Unknown tag — render as body text so nothing silently vanishes.
            pdf.set_font("Helvetica", "", SIZE_BODY)
            pdf.multi_cell(content_width, 5.5, text)

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
