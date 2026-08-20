# render-doc

Render any Markdown file to a print-quality A4 PDF.

No install step, no dependencies to manage: it needs Python 3 and Google Chrome, both of
which you already have. The script generates HTML in memory and drives Chrome headless.

```bash
python3 skills/render-doc/render-doc.py report.md
python3 skills/render-doc/render-doc.py 2026-08-18_working-name.md Report_For_Client.pdf
```

Once the plugin is installed you can also just ask Claude for a PDF of a Markdown file and
the skill takes over.

## Private notes in the same file

Everything from a `## Interna anteckningar` heading onward is dropped, as are HTML
comments. That lets one Markdown file hold both the document that goes to the recipient
and your own working notes on it, with no risk of the notes travelling along.

```markdown
# Offer

...the client-facing document...

## Interna anteckningar

Client pushed back on scope last time - keep the delivery boundary explicit. Never rendered.
```

## Supported Markdown

Headings, paragraphs, bold, italic, inline code, links, ordered and unordered lists,
tables, fenced code blocks, blockquotes, horizontal rules.

A table whose first row is empty renders without a header row, which gives the borderless
key/value layout used for document front matter. A blockquote containing a run of
underscores keeps its line breaks so fill-in forms survive; other blockquotes are joined
as wrapped prose.

## Limitations

The converter is regex-based rather than a full CommonMark implementation. It covers the
constructs above well and ignores the rest, so look at the output before sending it.

Page numbers and running headers are not implemented. Chrome does support `@page` margin
boxes including `counter(page)`, so they can be added; CSS positioned elements are not a
working substitute.

## Styling

Typography lives in the `CSS` constant at the top of the script: serif body text, sans
headings, A4 with 18-20mm margins. Edit it there.
