"""
Press Pause — Flask Web App

Group project for "AI: Problems and Possibilities."
Advocates for a pause on frontier AI development while we confront
the risks of misalignment, loss of human life, and sustainability.

The splash page greets visitors with a spinning Earth and a red
"pause" button; pressing it enters the mission page — a single
continuous-scroll document with a title, tagline, two content
sections (Mission Statement, Proposed Solution), and an authors
block at the bottom.

All text lives in content/ — editable as plain text with no code
changes needed. Save the file, refresh the page, done.
"""

import re
import os
from pathlib import Path

import markdown
from flask import Flask, render_template, Response

from bill_pdf import render_bill_pdf

HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

app = Flask(__name__)

CONTENT_DIR = Path(__file__).parent / "content"


def load_section(name: str) -> str:
    """
    Load content/<name>.md and render it to HTML.

    Html comments ('<!-- ... -->') are stripped so the editor's notes
    at the top of each file don't appear on the page.
    """
    md_path = CONTENT_DIR / f"{name}.md"
    if not md_path.exists():
        return ""
    raw = md_path.read_text(encoding="utf-8")
    raw = HTML_COMMENT_RE.sub("", raw)
    return markdown.markdown(
        raw,
        extensions=["extra", "sane_lists"],
    )


def load_line(name: str, default: str = "") -> str:
    """
    Load content/<name>.txt as a single line of plain text.
    Used for short fields like the page title and tagline.
    """
    txt_path = CONTENT_DIR / f"{name}.txt"
    if not txt_path.exists():
        return default
    return txt_path.read_text(encoding="utf-8").strip()


@app.route("/")
def splash():
    """Splash page — spinning globe + red pause button."""
    return render_template("splash.html")


@app.route("/mission")
def mission():
    """
    Single-page continuous-scroll site.
    All text is re-read from the content/ folder on every request,
    so edits show up on a page refresh with no restart needed.
    """
    return render_template(
        "mission.html",
        page_title=load_line("title", "Press Pause"),
        page_tagline=load_line("tagline", ""),
        mission_title=load_line("mission_title", "Mission Statement"),
        solution_title=load_line("solution_title", "Proposed Solution"),
        mission_html=load_section("mission"),
        solution_html=load_section("solution"),
        authors_html=load_section("authors"),
    )


@app.route("/bill.pdf")
def bill_pdf():
    """
    Serve The Bill as a downloadable PDF, regenerated on every request
    so it's always in sync with content/solution.md.
    """
    pdf_bytes = render_bill_pdf(CONTENT_DIR / "solution.md")
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            # "attachment" = trigger a download dialog rather than open
            # inline. Filename is what the browser suggests.
            "Content-Disposition": 'attachment; filename="ai-safety-oversight-act.pdf"',
            # Don't cache — the content file can change between deploys.
            "Cache-Control": "no-cache, max-age=0",
        },
    )


if __name__ == "__main__":
    # Local-dev entrypoint only. On Render, gunicorn imports the `app`
    # object directly and this block never runs — so debug=True here
    # only affects your machine, giving you template auto-reload.
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=True, host="0.0.0.0", port=port)
