---
name: render-doc
description: Render a Markdown file to a print-quality A4 PDF. Use when the user asks to "make a PDF of this", "render this to PDF", "export the document", "print-ready version", "skicka som PDF", "rendera till A4", or wants any .md turned into a document they can send to someone. Also use when a deliverable has been written as Markdown and the user needs the version that actually goes to the recipient.
allowed-tools: Read, Write, Edit, Bash, Glob
---

# Render a Markdown document to A4 PDF

Turns ordinary Markdown into a print-ready A4 PDF. Nothing to install: the only
requirements are Python 3 and Google Chrome, and the script drives Chrome headless.

## Run it

```bash
python3 "${CLAUDE_PLUGIN_DIR}/skills/render-doc/render-doc.py" <file.md> [out.pdf] [--sans] [--logo <image>] [--logo-align left|right] [--draft [TEXT]]
```

- `--sans` sets the body in Inter (Google Fonts, falls back to Helvetica Neue offline)
  instead of the default serif. Use it when the project or document asks for a sans serif.
- `--draft` lays a faint diagonal "Utkast" across every page; `--draft "Draft"` uses
  another word. For versions that circulate before the document is final.
- `--logo <image>` places the image on the first page above the title, top right by
  default or top left with `--logo-align left`. SVG or PNG; the file is embedded in the PDF. Use it for letterhead-style documents such as
  offers and invoices, where the project says where its logo lives.

Without an output path the PDF is written next to the source with the same stem. Give an
explicit output path when the recipient-facing filename should differ from the working
filename - which is often, since working files tend to be named `YYYY-MM-DD_slug.md`
while the thing you send should be named for what it is.

## What it handles

Headings (4 levels), paragraphs, bold, italic, inline code, links, ordered and unordered
lists, tables, fenced code blocks, blockquotes, horizontal rules.

Three behaviours worth knowing:

- A line holding only `\newpage` starts a new page (the pandoc convention). Use it for
  an appendix or a signature page that should not share a page with the body.
- A table whose first row is empty renders without a header row. That is the borderless
  key/value layout used for document front matter.
- A blockquote containing a run of underscores keeps its line breaks, because it is a
  fill-in form and the breaks are the layout. Other blockquotes are joined as wrapped
  prose.

## Two things are dropped automatically

Neither ever reaches the PDF:

- **everything from a `## Interna anteckningar` heading onward**
- **HTML comments**

This is the point of the tool, not a quirk. A deliverable can carry both the
recipient-facing document and the author's own working notes in one Markdown file, and the
notes cannot leak into what gets sent. When writing such a document, put the private
material under that exact heading.

## After rendering

1. **Read the PDF back** with the Read tool and look at it. The converter is regex-based,
   not a full Markdown implementation - unusual structures can come out wrong, and looking
   is the only way to know.
2. **Confirm the private section is gone** if the source had one.
3. Report the page count and the output path.

## Notes

- The Markdown file is the single source of truth. Never keep a hand-maintained HTML or
  PDF copy beside it. They drift, and the stale one is the one that gets sent.
- A `.print.html` temp file appears next to the source during the run and is removed
  afterwards. If a run fails partway, delete any leftover.
- Adjacent list items of different kinds - a `-` item directly followed by a `1.` item
  with no blank line between them - merge into one list of the first kind. Separate them
  with a blank line.
- Page numbers and running headers are not implemented. Chrome does support `@page`
  margin boxes including `counter(page)`, so they are possible; positioned elements are
  not a workable substitute and should not be attempted.
