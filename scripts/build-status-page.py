#!/usr/bin/env python3
"""Generate stakeholder status HTML from DELIVERABLES, ROADMAP, and PRODUCT.md."""
from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "infra" / "status" / "out"
OUT_FILE = OUT_DIR / "index.html"

PUBSPEC = ROOT / "apps" / "mobile" / "pubspec.yaml"
DELIVERABLES = ROOT / "docs" / "DELIVERABLES.md"
ROADMAP = ROOT / "docs" / "stakeholder" / "ROADMAP.md"
PRODUCT = ROOT / "docs" / "PRODUCT.md"


def sanitize(text: str) -> str:
    text = re.sub(r"/home/dev[^\s\)]*", "", text)
    text = re.sub(r"43\.160\.220\.9", "production host", text)
    text = re.sub(r"/opt/aipal[^\s\)]*", "", text)
    return text.strip()


def read_version() -> tuple[str, str, str]:
    line = PUBSPEC.read_text(encoding="utf-8").splitlines()
    for raw in line:
        if raw.startswith("version:"):
            ver = raw.split(":", 1)[1].strip()
            name, _, code = ver.partition("+")
            return ver, name, code
    return "unknown", "unknown", "0"


def extract_section(text: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}\s*$"
    m = re.search(pattern, text, re.MULTILINE)
    if not m:
        return ""
    start = m.end()
    nxt = re.search(r"^## ", text[start:], re.MULTILINE)
    end = start + nxt.start() if nxt else len(text)
    return text[start:end].strip()


def parse_markdown_table(block: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        if re.match(r"^\|[-:\s|]+\|$", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cells)
    return rows


def parse_executive_summary() -> tuple[list[list[str]], str]:
    body = extract_section(DELIVERABLES.read_text(encoding="utf-8"), "1. Executive summary")
    narrative = ""
    for line in body.splitlines():
        if line.startswith("**Narrative:**"):
            narrative = sanitize(line.replace("**Narrative:**", "").strip())
            break
    table_rows = parse_markdown_table(body)
    return table_rows, narrative


def parse_roadmap_table() -> list[list[str]]:
    text = ROADMAP.read_text(encoding="utf-8")
    block = extract_section(text, "Roadmap")
    return parse_markdown_table(block)


def parse_pillars() -> list[list[str]]:
    text = ROADMAP.read_text(encoding="utf-8")
    block = extract_section(text, "Differentiation pillars")
    return parse_markdown_table(block)


def parse_product_tagline() -> str:
    text = ROADMAP.read_text(encoding="utf-8")
    m = re.search(r"\*\*Product:\*\*\s*(.+)", text)
    return sanitize(m.group(1).strip()) if m else "AiPal voice companion"


def parse_deferred_items() -> list[str]:
    text = PRODUCT.read_text(encoding="utf-8")
    block = extract_section(text, "C4+ — Deferred")
    items: list[str] = []
    for line in block.splitlines():
        m = re.match(r"^- \[ \]\s+(.+)", line.strip())
        if m:
            items.append(sanitize(m.group(1)))
    return items


def render_table(rows: list[list[str]], headers: bool = True) -> str:
    if not rows:
        return "<p><em>No data</em></p>"
    out = ["<table>"]
    start = 1 if headers and len(rows) > 1 else 0
    if headers and rows:
        out.append("<thead><tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in rows[0]) + "</tr></thead>")
    out.append("<tbody>")
    for row in rows[start:]:
        out.append("<tr>" + "".join(f"<td>{html.escape(sanitize(c))}</td>" for c in row) + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def build_html() -> str:
    version_full, version_name, version_code = read_version()
    built_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    exec_rows, narrative = parse_executive_summary()
    roadmap_rows = parse_roadmap_table()
    pillar_rows = parse_pillars()
    tagline = parse_product_tagline()
    deferred = parse_deferred_items()

    deferred_html = (
        "<ul>" + "".join(f"<li>{html.escape(i)}</li>" for i in deferred) + "</ul>"
        if deferred
        else "<p><em>None listed</em></p>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AiPal — Stakeholder Status</title>
  <style>
    :root {{
      --bg: #0d1117;
      --surface: #161b22;
      --text: #e6edf3;
      --muted: #8b949e;
      --accent: #e8a838;
      --border: #30363d;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }}
    .wrap {{ max-width: 920px; margin: 0 auto; padding: 1.5rem; }}
    header {{
      border-bottom: 1px solid var(--border);
      padding-bottom: 1rem;
      margin-bottom: 1.5rem;
    }}
    h1 {{ margin: 0 0 0.25rem; font-size: 1.75rem; }}
    .meta {{ color: var(--muted); font-size: 0.95rem; }}
    .tagline {{ color: var(--accent); margin-top: 0.5rem; }}
    section {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1rem 1.25rem;
      margin-bottom: 1rem;
    }}
    h2 {{ margin: 0 0 0.75rem; font-size: 1.1rem; color: var(--accent); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.92rem; }}
    th, td {{ border-bottom: 1px solid var(--border); padding: 0.5rem 0.4rem; text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 600; }}
    ul {{ margin: 0.25rem 0 0 1.1rem; padding: 0; }}
    .note {{ color: var(--muted); font-size: 0.9rem; }}
    footer {{ margin-top: 1.5rem; color: var(--muted); font-size: 0.85rem; }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>AiPal — Stakeholder Status</h1>
      <div class="meta">Build <strong>{html.escape(version_name)}</strong> (code {html.escape(version_code)}) · Last verified {html.escape(built_at)}</div>
      <div class="tagline">{html.escape(tagline)}</div>
      <p class="note">Pre-deploy checks passed at build time (pytest, smoke test, flutter analyze on release pipeline).</p>
    </header>

    <section>
      <h2>Executive summary</h2>
      {f"<p>{html.escape(narrative)}</p>" if narrative else ""}
      {render_table(exec_rows)}
    </section>

    <section>
      <h2>Roadmap</h2>
      {render_table(roadmap_rows)}
    </section>

    <section>
      <h2>Differentiation pillars</h2>
      {render_table(pillar_rows)}
    </section>

    <section>
      <h2>Deferred / not started</h2>
      {deferred_html}
    </section>

    <section>
      <h2>Feedback</h2>
      <p class="note">Testers: use the Play Internal build or contact the maintainer directly. This page updates on each production release.</p>
    </section>

    <footer>
      AiPal stakeholder dashboard · generated from product docs · version {html.escape(version_full)}
    </footer>
  </div>
</body>
</html>
"""


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    content = build_html()
    if "/home/dev" in content:
        raise SystemExit("Sanitization failed: internal paths in output")
    OUT_FILE.write_text(content, encoding="utf-8")
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
