# 01: Product Spec

## 1. Vision

A fast, offline desktop PDF editor that does the 90% of everyday PDF jobs well: read, mark up, fill forms, sign, reorganize pages, redact, and make small text fixes, without uploading documents anywhere. Correctness of output (files open cleanly in Acrobat, Chrome, Preview, Edge) matters more than feature count.

## 2. Target users & core jobs

| User | Job to be done |
|---|---|
| Student | Highlight and comment on lecture notes and papers; merge assignment PDFs; export pages |
| Office worker | Fill and sign forms; reorder or delete pages of a scan; compress before emailing |
| Anyone handling private info | Permanently redact names/numbers before sharing |
| Engineer (domain fit) | Mark up datasheets and drawings; measure/annotate; extract a page range |

## 3. Feature list with priority

Priority: **P0** = MVP must-have · **P1** = v1.0 · **P2** = later/nice-to-have.

### 3.1 Viewing & navigation
| ID | Feature | Pri | Acceptance criteria |
|---|---|---|---|
| V1 | Open PDF via menu, drag-and-drop, CLI arg, recent files | P0 | Opens 1-page and 1,000-page files; first page visible < 1 s for typical files (under ~10 MB), < 1.5 s for the large reference file in §4 |
| V2 | Continuous vertical scroll, all pages | P0 | Smooth scrolling; only visible pages rendered |
| V3 | Zoom: in/out, fit width, fit page, 25%–800%, Ctrl+wheel | P0 | Zoom anchors on cursor position; text stays crisp after zoom settles |
| V4 | Page thumbnails sidebar | P0 | Click jumps to page; current page highlighted |
| V5 | Go to page (number box), Home/End/PgUp/PgDn | P0 | |
| V6 | Text search with hit highlighting, next/prev, match count | P0 | Case-insensitive default; hits highlighted on page; works across all pages without freezing UI |
| V7 | Outline/bookmarks panel (TOC) | P1 | Shows nested TOC; click navigates |
| V8 | Text selection & copy | P1 | Drag-select text, Ctrl+C copies in reading order |
| V9 | Single page / two-page spread view modes | P2 | |
| V10 | Dark mode UI (page content stays as-is) | P2 | |
| V11 | Rotate view (not file) | P2 | |
| V12 | Page labels in the page box | P1 | Shows "iv (4 of 120)" when the PDF defines labels; typing a label ("iv") or a number both work |
| V13 | Remember reading position per file | P1 | Reopening a file returns to its last page and zoom; cleared together with recent files |
| V14 | Night reading mode (invert page colors) | P2 | View-only, file unchanged; toggle in View menu; separate from V10 (dark UI) |
| V15 | Snapshot tool: copy a page region as an image | P1 | Drag a box → image on the clipboard at 2× screen resolution (or chosen DPI); also "Save as PNG…" |
| V16 | Attachments panel | P1 | Lists embedded files and file-attachment annotations (name, size); "Save as…" only on explicit action; never opened or run (doc 09) |

### 3.2 Annotation (standard PDF annotations, which other viewers can see and edit)
| ID | Feature | Pri | Acceptance criteria |
|---|---|---|---|
| A1 | Highlight text (select text → highlight), choose color | P0 | Saved as `/Highlight` annot with QuadPoints; visible in Acrobat/Chrome |
| A2 | Underline, strike-out, squiggly | P1 | Same as A1 |
| A3 | Sticky note (Text annot) with popup content | P0 | Author + content editable; icon placed where clicked |
| A4 | Free text box (typewriter) | P0 | Font size, color; editable after creation |
| A5 | Shapes: rectangle, ellipse, line, arrow | P1 | Stroke color, width, fill |
| A6 | Ink / freehand pen | P1 | Smooth strokes; stroke width/color |
| A7 | Select, move, resize, delete existing annotations (incl. ones made by other apps) | P0 | Handles shown on selection; Delete key removes |
| A8 | Annotation list sidebar with filter by type/page | P1 | Click jumps to annotation |
| A9 | Annotation properties panel (color, opacity, border, author, content) | P1 | |
| A10 | Flatten annotations (burn into page content) | P2 | |
| A11 | Measure tool: calibrate scale, then distance / perimeter / area | P1 | Scale set from a ratio ("1 in = 10 ft") or by drawing over a known dimension; results saved as Line/Polygon annotations with the measured value in their text, so other viewers show it (Acrobat's native `/Measure` format is out of scope for v1) |
| A12 | Export comments to Markdown | P1 | One file listing, in page order: each highlight's covered text, note/free-text content, author, page number; optional plain-text format |

### 3.3 Page organization
| ID | Feature | Pri | Acceptance criteria |
|---|---|---|---|
| P1 | Rotate page(s) 90° left/right | P0 | Sets `/Rotate`, no re-rendering of content needed in file |
| P2 | Delete page(s) | P0 | Multi-select in thumbnails |
| P3 | Reorder by drag in thumbnail panel | P0 | Undoable |
| P4 | Insert blank page / insert pages from another PDF | P1 | |
| P5 | Merge multiple PDFs (dialog with ordered list) | P0 | Keeps bookmarks where feasible; links preserved |
| P6 | Split / extract pages (range syntax `1-3,7,10-`) | P0 | Writes new file(s) |
| P7 | Crop pages (set CropBox) | P2 | |
| P8 | Duplicate page | P2 | |

### 3.4 Forms
| ID | Feature | Pri | Acceptance criteria |
|---|---|---|---|
| F1 | Detect and fill AcroForm fields (text, checkbox, radio, combo, list) | P0 | Values persist and display in Acrobat/Chrome (appearance streams regenerated) |
| F2 | Tab between fields | P1 | Follows field order |
| F3 | Create fields (text, checkbox) | P2 | |
| F4 | Flatten form | P2 | |
| F5 | XFA forms: detect and warn ("not supported, view-only") | P1 | Clear message, no crash |

### 3.5 Content editing
| ID | Feature | Pri | Acceptance criteria |
|---|---|---|---|
| C1 | Add new text to page content (not an annotation) | P1 | Choose font (base-14 + bundled fonts), size, color |
| C2 | Add image (PNG/JPG) to page, position and scale | P1 | Aspect ratio lock by default |
| C3 | Visual signature: draw / type / import image, place as stamp | P0 | Saved signatures reusable; NOT a cryptographic signature (label it honestly) |
| C4 | Edit existing text: replace a span's text (limited, see doc 06) | P1 | Works for simple single-line spans; warns when font lacks glyphs |
| C5 | Whiteout (cover area with white rectangle) | P1 | Labeled clearly as "cover", not "redact" |
| C6 | Headers/footers/page numbers/watermark | P2 | |
| C7 | Digital signatures (PKI, cryptographic) | P2 | Out of scope for v1 |

### 3.6 Redaction
| ID | Feature | Pri | Acceptance criteria |
|---|---|---|---|
| R1 | Mark area for redaction (drag rectangle) | P0 | Shown as outlined region before applying |
| R2 | Mark search results for redaction (e.g. a name, regex for SSN/email/phone) | P1 | Review list before apply |
| R3 | Apply redactions | P0 | Text under area is **gone** from extraction; images under area are blanked; lines/shapes fully inside the area are removed (option: also remove ones that touch it); confirmation dialog explaining it's permanent |
| R4 | Sanitize document: remove metadata, hidden text, JavaScript, embedded files, comments | P1 | Options dialog |

### 3.7 File operations
| ID | Feature | Pri | Acceptance criteria |
|---|---|---|---|
| S1 | Save (incremental when possible) / Save As | P0 | Atomic write; original never corrupted on crash |
| S2 | Unsaved-changes prompt on close/open | P0 | |
| S3 | Open password-protected PDFs | P0 | Password prompt; wrong password retry |
| S4 | Save with password (AES-256) and permissions | P1 | |
| S5 | Optimize / compress (garbage collect, deflate, image downsample) | P1 | Shows before/after size |
| S6 | Export page(s) as PNG/JPG at chosen DPI | P1 | |
| S7 | Print | P2 | via QPrinter rendering pages |
| S8 | Autosave/crash recovery | P2 | |
| S9 | Document properties (title, author, subject, keywords) | P1 | |
| S10 | History panel (list of edits; click to go back to any point) | P1 | Shows every undoable edit with a readable label; clicking a row undoes/redoes to that point; saved state marked |

### 3.8 Tools
| ID | Feature | Pri | Acceptance criteria |
|---|---|---|---|
| T1 | OCR "make searchable" for scanned pages | P2 | Adds an invisible text layer so search, select, highlight and redact work; page looks unchanged; needs Tesseract installed (detected, with install hint if missing); runs in the background process with progress; undoable |
| T2 | Compare two versions of a PDF | P2 | Pick a second file; pages shown side by side or overlaid; changed regions highlighted (from a pixel diff of renders); per-page list of text added/removed; read-only |

## 4. Non-functional requirements

- **Performance:** opening a 500-page, 50 MB PDF shows page 1 in under 1.5 s on a mid-range laptop; scrolling never blocks input for more than 50 ms; memory stays under ~1 GB on that file.
- **Fidelity:** Output must open without warnings in Adobe Acrobat Reader, Chrome, Firefox (pdf.js), macOS Preview. Annotations created must be editable in Acrobat.
- **Safety:** No data loss on crash during save. Redaction verified by test. No network access at all.
- **Accessibility:** Keyboard shortcuts for all main actions; tooltips; respects OS scaling (HiDPI).
- **Platforms:** Windows 10/11 and macOS 13+ first; Linux best-effort.

## 5. Keyboard shortcuts (defaults)

| Action | Shortcut |
|---|---|
| Open / Save / Save As | Ctrl+O / Ctrl+S / Ctrl+Shift+S |
| Undo / Redo | Ctrl+Z / Ctrl+Y (Win) · Ctrl+Shift+Z |
| Find | Ctrl+F; F3 / Shift+F3 next/prev (in the find box: Enter / Shift+Enter); Esc closes the find bar |
| Copy selected text | Ctrl+C |
| Show / hide the sidebar | F4 |
| Zoom in / out / 100% / fit page / fit width | Ctrl+= / Ctrl+- / Ctrl+0 / Ctrl+1 / Ctrl+2 |
| Select tool / Hand tool | V / H (Space held = temporary hand) |
| Highlight / Note / Text box / Pen | Ctrl+Alt+H / N / T / P |
| Delete selected | Delete |
| Next/prev page | PgDn / PgUp |
| First/last page | Home / End (also Ctrl+Home / Ctrl+End) |

(Qt maps Ctrl→Cmd on macOS automatically via `QKeySequence.StandardKey`; prefer standard keys where they exist.)

## 6. Explicitly out of scope (v1)

- Full reflowing "Word-like" editing of paragraphs in existing PDFs (technically very hard; see doc 03 §7)
- XFA form filling
- Cryptographic digital signatures and certificate validation
- PDF/A conformance validation and conversion
- Converting PDF ↔ Word/Excel
- Cloud sync, accounts, collaboration
- Creating PDFs from scratch as a document authoring tool (beyond blank pages)

## 7. UI layout sketch

```
┌───────────────────────────────────────────────────────────────────────┐
│ Menu: File  Edit  View  Annotate  Pages  Forms  Tools  Help           │
├───────────────────────────────────────────────────────────────────────┤
│ Toolbar: [Open][Save] | [Undo][Redo] | [Select][Hand] | [HL][Note]    │
│          [Text][Pen][Shape] | [Redact] | zoom [-][125%▼][+] | [🔍____] │
├──────────┬────────────────────────────────────────────┬───────────────┤
│ Sidebar  │                                            │ Properties    │
│ tabs:    │            Page canvas (QGraphicsView)     │ panel         │
│ Thumbs   │            pages stacked vertically        │ (context:     │
│ Outline  │            gray background, drop shadow    │ selected      │
│ Annots   │                                            │ annotation /  │
│ Search   │                                            │ field / tool) │
│ History  │                                            │               │
│ Attach.  │                                            │               │
├──────────┴────────────────────────────────────────────┴───────────────┤
│ Status: Page 3 / 120 · 125% · "Unsaved changes" · tool hint           │
└───────────────────────────────────────────────────────────────────────┘
```
