#!/usr/bin/env python3
"""
Render a Markdown document to a print-quality A4 PDF.

    python3 render-doc.py kompendium.md [ut.pdf]

Generic counterpart to consultant-profiles/render-cv.py, which only understands
the CV structure. This one takes ordinary Markdown - headings, paragraphs, lists,
tables, code blocks, blockquotes, rules - and lays it out for A4.

The Markdown stays the single source of truth. No HTML copy is kept, so the two
cannot drift apart.

Everything from a "## Interna anteckningar" heading onward is dropped, as are
HTML comments - neither belongs in a document that goes to a client.
"""

import html
import re
import subprocess
import sys
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
  @page { size: A4; margin: 20mm 18mm 18mm 18mm; }
  :root {
    --ink: #16181a; --body: #2e3236; --muted: #6b7178;
    --rule: #d9dcdf; --accent: #5d6b52; --wash: #f5f6f4;
  }
  * { box-sizing: border-box; }
  body {
    font-family: "Source Serif 4", Georgia, "Times New Roman", serif;
    font-size: 10.2pt; line-height: 1.55; color: var(--body);
    margin: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }
  h1, h2, h3, h4 {
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    color: var(--ink); line-height: 1.25; margin: 0;
  }
  h1 { font-size: 19pt; letter-spacing: -0.2pt; margin-bottom: 4mm; }
  h2 {
    font-size: 12.5pt; margin: 9mm 0 3mm; padding-bottom: 1.6mm;
    border-bottom: 1.2px solid var(--rule); break-after: avoid;
  }
  h3 {
    font-size: 10.8pt; margin: 6mm 0 2mm; color: var(--accent);
    break-after: avoid;
  }
  h4 { font-size: 10pt; margin: 4.5mm 0 1.5mm; break-after: avoid; }
  p { margin: 0 0 2.6mm; orphans: 2; widows: 2; }
  ul, ol { margin: 0 0 2.6mm; padding-left: 5.5mm; }
  li { margin-bottom: 1.1mm; }
  a { color: var(--accent); text-decoration: none; }
  strong { color: var(--ink); }
  hr { border: 0; border-top: 1px solid var(--rule); margin: 6mm 0; }
  blockquote {
    margin: 0 0 3mm; padding: 2mm 0 2mm 4mm;
    border-left: 2px solid var(--accent); color: var(--muted);
  }
  code {
    font-family: "SF Mono", Menlo, Consolas, monospace;
    font-size: 8.6pt; background: var(--wash); padding: 0.3mm 1mm;
    border-radius: 1.5px;
  }
  pre {
    background: var(--wash); border: 1px solid var(--rule); border-radius: 2px;
    padding: 2.5mm 3mm; margin: 0 0 3mm; overflow: hidden;
    break-inside: avoid;
  }
  pre code {
    background: none; padding: 0; font-size: 8.4pt; line-height: 1.45;
    white-space: pre-wrap; word-break: break-word;
  }
  table {
    width: 100%; border-collapse: collapse; margin: 0 0 3.5mm;
    font-size: 9.1pt; break-inside: avoid;
  }
  th, td {
    text-align: left; vertical-align: top; padding: 1.6mm 2.2mm;
    border-bottom: 1px solid var(--rule);
  }
  th {
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 8.4pt; text-transform: uppercase; letter-spacing: 0.4pt;
    color: var(--muted); border-bottom: 1.2px solid var(--rule);
  }
  table table { display: none; }
"""

INLINE_CODE = re.compile(r"`([^`]+)`")
BOLD = re.compile(r"\*\*([^*]+)\*\*")
ITALIC = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?!\*)")
LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def inline(text):
    """Escape, then apply inline Markdown. Code spans keep their escaped text."""
    out = html.escape(text, quote=False)
    stash = []

    def keep(m):
        stash.append(m.group(1))
        return f"\x00{len(stash) - 1}\x00"

    out = INLINE_CODE.sub(keep, out)
    out = LINK.sub(r'<a href="\2">\1</a>', out)
    out = BOLD.sub(r"<strong>\1</strong>", out)
    out = ITALIC.sub(r"<em>\1</em>", out)
    out = re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{stash[int(m.group(1))]}</code>", out)
    return out


def is_table_row(line):
    return line.lstrip().startswith("|")


def is_table_divider(line):
    return bool(re.fullmatch(r"\|[\s:|-]+\|?", line.strip())) and "-" in line


def split_row(line):
    cells = line.strip().strip("|").split("|")
    return [c.strip() for c in cells]


def render_table(rows):
    """First row is the header unless it is empty - borderless key/value tables
    in these documents open with an empty header row."""
    head, body = rows[0], rows[1:]
    out = ["<table>"]
    if any(c for c in head):
        out.append("<thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead>")
    else:
        body = rows[1:]
    out.append("<tbody>")
    for r in body:
        out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def to_html(md):
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    cut = re.search(r"^##\s+Interna anteckningar.*$", md, flags=re.M)
    if cut:
        md = md[: cut.start()]

    lines = md.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]

        if line.strip().startswith("```"):
            lang, i = line.strip()[3:], i + 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(buf), quote=False) + "</code></pre>")
            continue

        if is_table_row(line) and i + 1 < len(lines) and is_table_divider(lines[i + 1]):
            rows = [split_row(line)]
            i += 2
            while i < len(lines) and is_table_row(lines[i]):
                rows.append(split_row(lines[i]))
                i += 1
            out.append(render_table(rows))
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            lvl = min(len(m.group(1)), 4)
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1
            continue

        if re.fullmatch(r"\s*([-*_])\s*\1\s*\1[\s\-*_]*", line):
            out.append("<hr>")
            i += 1
            continue

        if line.lstrip().startswith(">"):
            buf = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                buf.append(lines[i].lstrip()[1:].strip())
                i += 1
            # A blockquote holding a run of underscores is a fill-in form, not
            # wrapped prose - its line breaks are the layout and must survive.
            if any(re.search(r"_{5,}", b) for b in buf):
                body = "<br>".join(inline(b) if b else "&nbsp;" for b in buf)
            else:
                body = inline(" ".join(b for b in buf if b))
            out.append(f"<blockquote><p>{body}</p></blockquote>")
            continue

        m = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)$", line)
        if m:
            ordered = not m.group(2) in "-*+"
            tag = "ol" if ordered else "ul"
            items, i = [], i
            while i < len(lines):
                mm = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)$", lines[i])
                if mm:
                    items.append(mm.group(3))
                    i += 1
                elif lines[i].startswith(("  ", "\t")) and lines[i].strip() and items:
                    items[-1] += " " + lines[i].strip()
                    i += 1
                else:
                    break
            out.append(f"<{tag}>" + "".join(f"<li>{inline(t)}</li>" for t in items) + f"</{tag}>")
            continue

        if not line.strip():
            i += 1
            continue

        buf = []
        while i < len(lines) and lines[i].strip() and not re.match(
            r"^(#{1,6}\s|\s*[-*+]\s|\s*\d+\.\s|>|\|)", lines[i]
        ) and not lines[i].strip().startswith("```"):
            buf.append(lines[i].strip())
            i += 1
        if buf:
            out.append(f"<p>{inline(' '.join(buf))}</p>")
        else:
            i += 1

    return "\n".join(out)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__.strip())
    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".pdf")

    body = to_html(src.read_text())
    title = html.escape(src.stem)
    page = (
        f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>"
        f"<style>{CSS}</style></head><body>{body}</body></html>"
    )
    tmp = src.with_suffix(".print.html")
    tmp.write_text(page)

    subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={out}", f"file://{tmp.resolve()}"],
        check=True, capture_output=True,
    )
    tmp.unlink()
    print(f"Wrote {out} ({out.stat().st_size // 1024} kB)")


if __name__ == "__main__":
    main()
