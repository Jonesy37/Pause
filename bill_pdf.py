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


# Helvetica (a PDF core font) doesn't cover the curly-quote / em-dash /
# ellipsis glyphs that editors like Google Docs love to auto-insert.
# Rather than ship a 200 KB Unicode TTF with the app, map the small set
# of punctuation we actually see in the source to plain ASCII before
# writing. fpdf2's multi_cell tolerates most of these silently, but
# write() raises, so the sanitizer keeps both paths safe.
_PDF_CHAR_MAP = {
    "\u2014": "-",      # em dash
    "\u2013": "-",      # en dash
    "\u2018": "'",      # left single quote
    "\u2019": "'",      # right single quote / apostrophe
    "\u201C": '"',      # left double quote
    "\u201D": '"',      # right double quote
    "\u2026": "...",    # horizontal ellipsis
    "\u00A0": " ",      # non-breaking space
    "\u200B": "",       # zero-width space
    "\u2011": "-",      # non-breaking hyphen
}


def _sanitize_for_pdf(text: str) -> str:
    for bad, good in _PDF_CHAR_MAP.items():
        text = text.replace(bad, good)
    return text


TIP_RE = re.compile(
    r'<span\s+class="tip"[^>]*>(.*?)</span>\s*</span>',
    re.DOTALL | re.IGNORECASE,
)
TIP_BODY_SPLIT_RE = re.compile(
    r'<span\s+class="tip-body"[^>]*>', re.IGNORECASE
)
ANCHOR_RE = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE)


class _FootnoteCollector:
    """
    Accumulates one numbered footnote per distinct source URL found
    inside bill tooltips. The same URL cited twice in the bill gets
    the same footnote number so the reference list stays tidy.

    Each call to flatten_tooltip returns the visible phrase with the
    footnote marker(s) appended, e.g. "Air-gapped[1]" or, for multi-
    source tips, "self-replicate[2][3]".
    """

    def __init__(self) -> None:
        self.by_url: dict[str, int] = {}
        self.entries: list[tuple[int, str, str]] = []  # (num, label, url)

    def _register(self, url: str, label: str) -> int:
        existing = self.by_url.get(url)
        if existing is not None:
            return existing
        num = len(self.entries) + 1
        self.by_url[url] = num
        self.entries.append((num, label, url))
        return num

    def flatten_tooltip(self, match: re.Match) -> str:
        """
        <span class="tip">visible<span class="tip-body">
            <a href="URL1">Label1</a>
            <a href="URL2">Label2</a>
        </span></span>
            -->
        "visible[1][2]"  (and records the two sources for later)
        """
        inner = match.group(1)
        # Split off the visible phrase (before the tip-body) from the
        # citation block (inside the tip-body).
        parts = TIP_BODY_SPLIT_RE.split(inner, maxsplit=1)
        visible_html = parts[0]
        body_html = parts[1] if len(parts) > 1 else ""

        visible = re.sub(r"<[^>]+>", "", visible_html).strip()

        markers: list[str] = []
        for url, label_html in ANCHOR_RE.findall(body_html):
            label = re.sub(r"<[^>]+>", "", label_html).strip()
            num = self._register(url, label)
            marker = f"[{num}]"
            if marker not in markers:
                # Guard against the same source being linked twice inside
                # one tip (e.g. same URL with two labels) — one marker is
                # enough at the call site.
                markers.append(marker)
        return visible + "".join(markers)


def _flatten_inline(html: str, fn: _FootnoteCollector) -> str:
    """
    Resolve inline tags down to plain text that's safe for PDF output.
    Tooltip sources are collected into `fn` and replaced with numeric
    footnote markers rather than breaking the flow of the sentence with
    inline [source: URL] text.
    """
    # Replace .tip pop-ups with "visible[N]" markers, collecting sources.
    html = TIP_RE.sub(fn.flatten_tooltip, html)
    # Flatten any stray anchors (outside tips) to 'label (URL)'.
    html = ANCHOR_RE.sub(lambda m: f"{re.sub(r'<[^>]+>', '', m.group(2))} ({m.group(1)})", html)
    # Drop any remaining tags (e.g. stray <span>, <em>, <strong>).
    html = re.sub(r"<[^>]+>", "", html)
    # Collapse whitespace introduced by the source file's indentation.
    html = re.sub(r"\s+", " ", html)
    return _sanitize_for_pdf(unescape(html).strip())


def parse_bill(md_path: Path) -> tuple[list[tuple[str, str]], list[tuple[int, str, str]]]:
    """
    Return (blocks, footnotes).
    - blocks: ordered (kind, text) pairs — kind is the CSS class.
    - footnotes: ordered (num, label, url) entries to render at the end.
    """
    raw = md_path.read_text(encoding="utf-8")
    raw = COMMENT_RE.sub("", raw)
    fn = _FootnoteCollector()
    blocks: list[tuple[str, str]] = []
    for tag, cls, inner in BLOCK_RE.findall(raw):
        # Keep only the first class token (e.g. "bill-title" from
        # "bill-title extra-class") since that's what we key off.
        kind = cls.split()[0]
        blocks.append((kind, _flatten_inline(inner, fn)))
    return blocks, fn.entries


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
    blocks, footnotes = parse_bill(md_path)

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

    # -- Sources section -----------------------------------------------
    # Numbered list at the end of the PDF. Each entry corresponds to a
    # [N] marker that appeared in the bill body above. Starts on a fresh
    # page so the references don't get awkwardly split across a column
    # break, and so readers can always flip to the back for citations.
    if footnotes:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", SIZE_HEADING + 1)
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(content_width, 7, "Sources", align="C")
        pdf.ln(3)

        pdf.set_font("Helvetica", "I", SIZE_BODY - 2)
        pdf.set_text_color(90, 90, 90)
        pdf.multi_cell(
            content_width,
            4.5,
            "Each [N] marker in the bill text corresponds to one entry below.",
            align="C",
        )
        pdf.ln(4)

        for num, label, url in footnotes:
            safe_label = _sanitize_for_pdf(label) if label else "(no label)"
            safe_url   = _sanitize_for_pdf(url)   if url   else ""

            # "[N] Label" on one wrapping line, URL on a hanging-indented
            # line below. multi_cell (not write) because it tolerates the
            # small unicode-punctuation slips our sanitizer might miss and
            # because it handles wrapping long labels for free.
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Helvetica", "", SIZE_BODY)
            pdf.multi_cell(content_width, 5.5, f"[{num}] {safe_label}")

            if safe_url:
                pdf.set_x(MARGIN_MM + 6)   # slight hanging indent under the label
                pdf.set_font("Helvetica", "I", SIZE_BODY - 1)
                pdf.set_text_color(60, 90, 170)
                pdf.multi_cell(content_width - 6, 5, safe_url, link=safe_url)
            pdf.ln(1.5)

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
