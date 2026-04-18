"""
Press Pause — Flask Web App

Group project for "AI: Problems and Possibilities."
Advocates for a pause on frontier AI development while we confront
the risks of misalignment, loss of human life, and sustainability.

The splash page greets visitors with a spinning Earth and a red
"pause" button; pressing it enters the site at the mission page,
which is a continuous-scroll document with three sections:
Mission Statement, The Research, Proposed Solution.

Section text lives in content/*.md — editable as plain text with
no code changes needed. Save the file, refresh the page, done.
"""

import re
import os
from pathlib import Path

import markdown
from flask import Flask, render_template

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


@app.route("/")
def splash():
    """Splash page — spinning globe + red pause button."""
    return render_template("splash.html")


@app.route("/mission")
def mission():
    """
    Single-page continuous-scroll site: mission / research / solution.
    All section text is read from the content/ folder on every request,
    so edits show up on a page refresh with no restart needed.
    """
    return render_template(
        "mission.html",
        mission_html=load_section("mission"),
        research_html=load_section("research"),
        solution_html=load_section("solution"),
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=False, host="0.0.0.0", port=port)
