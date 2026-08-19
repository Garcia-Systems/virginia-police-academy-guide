# PDF Build

## Architecture

Canonical content remains in language-specific Markdown. `book_manifest.py` is the single deterministic ordering contract for front matter, 22 chapters, appendices, titles, and output names. `scripts/build-pdf.sh` is the stable interface; `scripts/build_pdf.py` validates and assembles the selected edition. No manually concatenated book file is maintained.

The dependency-free builder targets foundation and review builds in constrained environments. It emits PDF 1.7 directly with US Letter pages, professional margins, a title/language page, each canonical file beginning on a new page, running chapter heads, page numbers, WinAnsi Spanish glyph support, basic Markdown headings/paragraphs/lists/quotes/tables, and clickable `http(s)` links. Future artwork can live in `images/chapters/`; image rendering is a known foundation limitation.

## Prerequisite

- Python 3.9 or newer (standard library only)

No network access, package installation, Pandoc, browser, or LaTeX distribution is required. Consequently a clean checkout with Python can reproduce the skeleton PDFs.

## Build

From the repository root:

```sh
./scripts/build-pdf.sh en
./scripts/build-pdf.sh es
```

Outputs:

- `dist/police-academy-virginia-en.pdf`
- `dist/academia-de-policia-virginia-es.pdf`

Generated PDFs are ignored; release automation may archive them.

## Validation and failure behavior

The builder rejects unsupported languages, any missing manifest-listed file, a chapter count other than 22, or a source file lacking a level-one title. Validation without rendering is available:

```sh
python3 scripts/build_pdf.py en --validate-only
python3 scripts/build_pdf.py es --validate-only
```

For post-build inspection when Poppler is installed:

```sh
pdfinfo dist/police-academy-virginia-en.pdf
pdfinfo dist/academia-de-policia-virginia-es.pdf
pdftotext dist/police-academy-virginia-en.pdf dist/en.txt
pdftotext dist/academia-de-policia-virginia-es.pdf dist/es.txt
```

Check that both PDFs parse, use Letter size, show their language-specific contents and all chapter titles in manifest order, retain `Guía`, `Policía`, `Año`, and other Spanish characters, and include `/Subtype /Link` annotations for external links. Missing-file behavior can be tested safely in a temporary clean copy, as documented in the project validation script.

## Current limitations and future extension

This lightweight renderer deliberately supports the book's current skeleton rather than all CommonMark. It has no images, internal TOC links/bookmarks, footnotes, tagged-PDF accessibility tree, font embedding, hyphenation, or sophisticated table layout. Before substantive chapters require those features, compare the inaccessible Inside Globant reference implementation (see `docs/REFERENCE_ARCHITECTURE.md`) and decide whether to extend this renderer or adopt its proven backend while preserving the manifest and shell interface.
