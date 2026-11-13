# 03: PDF Fundamentals (what you must understand before editing PDFs)

A PDF is **not** a document format like .docx. It is a **page description format**: a set of instructions saying "draw glyph #37 of font F1 at (72, 700)". There are no paragraphs, no lines, often not even words. Every design decision in this editor follows from that.

## 1. File structure

```
%PDF-1.7                      ← header
1 0 obj  << /Type /Catalog /Pages 2 0 R /AcroForm 9 0 R >>  endobj
2 0 obj  << /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>    endobj
3 0 obj  << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]
            /Resources << /Font << /F1 5 0 R >> >>
            /Contents 6 0 R /Annots [10 0 R] /Rotate 0 >>    endobj
6 0 obj  << /Length 44 /Filter /FlateDecode >> stream ...compressed drawing ops... endstream endobj
...
xref                          ← table: byte offset of each object
trailer << /Root 1 0 R /Info 7 0 R /Encrypt ... >>
startxref 12345
%%EOF
```

Key ideas:
- **Objects** are numbered (`3 0 obj` = object 3, generation 0). This number is the **xref**. PyMuPDF exposes it everywhere (`annot.xref`, `page.xref`, `doc.xref_object(n)`).
- **Indirect references** `5 0 R` point to other objects. The doc is a graph rooted at the **Catalog**.
- **Streams** hold binary data (page drawing instructions, images, fonts), usually compressed (`/FlateDecode`).
- **Object types:** dictionary `<< >>`, array `[ ]`, name `/Name`, string `(text)` or `<hex>`, number, boolean, null, reference.

### Incremental updates
A PDF can be modified by **appending** new versions of changed objects plus a new xref section at the end. The original bytes stay untouched. Consequences:
- Saving incrementally is fast and preserves existing digital signatures' validity for the original bytes.
- "Deleted" content may still be **physically present** in older revisions inside the file. **This is why redaction must be followed by a full (non-incremental) save with garbage collection**; otherwise the old text object may still be recoverable. (doc 06 §R, doc 07 §6)

### Object streams & xref streams (PDF 1.5+)
Objects can be packed inside compressed "object streams", with a compressed xref stream. PyMuPDF handles both transparently; `use_objstms=1` in `save()` produces smaller files.

## 2. Page tree and page boxes

Each page has boxes (rectangles in points, `[x0 y0 x1 y1]`):

| Box | Meaning | Use in editor |
|---|---|---|
| **MediaBox** | Physical page size | Always present (may be inherited from parent) |
| **CropBox** | Visible region; defaults to MediaBox | **What viewers show.** PyMuPDF's `page.rect` is based on CropBox |
| BleedBox / TrimBox / ArtBox | Print production | Ignore except preserving |

`/Rotate` (0, 90, 180, 270) rotates the *display* of the page clockwise. Content coordinates are not changed.

Common sizes: US Letter 612×792, A4 595×842 (points; 72 pt = 1 inch).

## 3. Coordinates (the #1 source of bugs)

### 3.1 Three coordinate systems you'll meet

1. **PDF native user space:** origin **bottom-left**, y goes **up**. This is what the raw file contains.
2. **PyMuPDF space:** origin **top-left** of the (unrotated) page, y goes **down**. PyMuPDF converts for you: every `Rect`, `Point`, `Quad` you get from or give to PyMuPDF is in this space. **Use this one everywhere in core.**
3. **Screen/scene space:** pixels, after zoom and rotation, offset by the page's position in the scroll view.

### 3.2 Rotation
`page.rect` reflects rotation (a portrait page with `/Rotate 90` has a landscape `page.rect`), but annotation rects, text bboxes, and insertion points are in **unrotated** coordinates. Verified behavior:

```python
page.set_rotation(90)
page.rect          # Rect(0, 0, 792, 612)  ← rotated, what the user sees
page.mediabox      # Rect(0, 0, 612, 792)  ← unrotated
pymupdf.Point(72, 72) * page.rotation_matrix   # → Point(720, 72): unrotated → rotated (display) space
```

Rules:
- Unrotated → displayed: `p * page.rotation_matrix`
- Displayed → unrotated (e.g. a mouse click): `p * page.derotation_matrix`
- Rendered pixmaps already show the rotation.

So the UI conversion for a click is:
`scene px → subtract page item offset → divide by zoom → (displayed PDF point) → × derotation_matrix → unrotated PDF point → core`.

### 3.3 Non-zero MediaBox origin
Some PDFs have `MediaBox [0 0 612 792]` but CropBox `[30 30 582 762]`, or MediaBox not starting at 0. PyMuPDF normalizes `page.rect` to start at (0,0) relative to the CropBox; `page.cropbox_position` gives the offset. Test with such a fixture (doc 08).

### 3.4 Units
1 pt = 1/72 inch. Render at zoom `z` → `Matrix(z, z)` → pixel size = `page.rect.width * z`. For HiDPI multiply by device pixel ratio. DPI equivalent = 72 × z.

## 4. Content streams (how pages draw)

A page's `/Contents` stream is a list of **operators** in postfix notation:

```
q                          % save graphics state
1 0 0 1 72 700 cm          % transform matrix (translate)
BT                         % begin text
/F1 12 Tf                  % font F1 at 12 pt
0 0 Td                     % position
(Hello) Tj                 % show string "Hello"
ET                         % end text
0.5 g 100 100 200 50 re f  % gray fill rectangle
/Im1 Do                    % draw image XObject Im1
Q                          % restore state
```

Important consequences:
- Text can be split arbitrarily: `[(He) 20 (llo)] TJ` with kerning, or each letter positioned separately, or words drawn out of reading order.
- **There is no "paragraph" object.** Reading order and line grouping are *inferred* by the text extractor.
- Spaces are often not characters at all, just gaps. Extractors guess them.
- **Form XObjects** are reusable sub-content (logos, headers) that can be drawn on many pages; editing one changes all pages using it.
- Inspect a page's raw content in dev with `page.read_contents()` (bytes) or `doc.xref_stream(xref)`.

## 5. Fonts and text encoding (why text editing is hard)

- A text-showing operator draws **glyph codes**, not Unicode. The font's encoding (and an optional `/ToUnicode` CMap) maps codes → Unicode for extraction. If ToUnicode is missing or wrong, extraction gives garbage even though the page looks fine.
- **Embedded fonts are usually subsets**: only glyphs actually used are included (font names like `ABCDEF+Calibri`). If the original text never used "Z", the embedded font **has no Z glyph**. You cannot type a Z in that font.
- **Base-14 fonts** (Helvetica, Times-Roman, Courier, Symbol, ZapfDingbats + bold/italic variants) are guaranteed available in every viewer without embedding, but only support Latin-1-ish characters.
- Font types: Type 1, TrueType, Type 3 (glyphs drawn by PDF operators), CID/Type 0 (CJK, large charsets).
- To add new text safely: use base-14 for Latin text, or **embed a full font file** you ship (e.g. Noto Sans) via `page.insert_font(fontname=..., fontfile=...)` / `fontbuffer=`. Run `doc.subset_fonts()` before saving to shrink.

## 6. Annotations vs page content

| | Annotation | Page content |
|---|---|---|
| Where it lives | `/Annots` array on the page, separate objects | Inside `/Contents` stream |
| Editable by other viewers | Yes (move, delete, change color) | Only by PDF editors |
| Has appearance stream (`/AP`) | Yes; this is what's actually drawn | n/a |
| Examples | Highlight, Text (sticky note), FreeText, Ink, Square, Circle, Line, Polygon, Stamp, Link, Widget (form field), Redact | Original text, images, vector drawings |

**Appearance streams:** an annotation's look is a mini content stream in `/AP /N`. If you change an annotation's properties you must regenerate it; in PyMuPDF that's `annot.update()`. Forgetting `update()` = changes don't show in other viewers.

**Flattening** = drawing the appearance into page content and deleting the annotation (irreversible).

Annotation flags matter: `Hidden`, `Print`, `NoView`, `ReadOnly`, `Locked`. Set `Print` on annotations users expect to print.

Popups: a `Text` annot has an associated `/Popup` annot for the note window. PyMuPDF manages this via `annot.set_popup()` / `set_open()`.

## 7. Why "edit text like Word" is not realistically achievable

To change "Hello world" to "Hello there, world" in place you'd need to:
1. Find which content-stream operators drew those glyphs (may be split across many operators and even XObjects).
2. Ensure the font has the new glyphs (subset fonts usually don't).
3. Re-layout: the new text is longer; the rest of the line and the paragraph below won't move, because the PDF has no layout engine. Every following line is absolutely positioned.
4. Preserve kerning, character spacing, word spacing, text rise, rendering mode, clipping.

**Our pragmatic approach (C4):** "Replace span" = redact the span's area (removing original glyphs; text-only redaction that leaves images/graphics) → insert new text at the same baseline with the closest available font and size → warn if width overflows. Works well for form-like documents, invoices, labels; poor for justified paragraphs. Be honest in the UI ("Edits replace a line of text; layout will not reflow"). Details: doc 06 §C4.

## 8. Interactive forms (AcroForm)

- `/AcroForm` in the catalog lists **fields**. Each field has one or more **widget annotations** (the visual boxes) on pages. A radio group = one field, many widgets.
- Field types: `/Tx` text, `/Btn` (checkbox, radio, push button), `/Ch` (combo, list), `/Sig` signature.
- Field value `/V`; widget appearance `/AP` with states (`/On`/`Off` names vary per checkbox! Use the widget's `on_state()`).
- `/NeedAppearances true` asks viewers to regenerate appearances; unreliable. PyMuPDF's `widget.update()` regenerates them; always do that.
- Fields can be hierarchical (`parent.child` full names).
- **XFA** forms (XML Forms Architecture, from Adobe LiveCycle) are a different technology embedded in the PDF. Most non-Adobe tools can't render or fill them properly. "Dynamic XFA" PDFs often show only "Please wait…" in non-Adobe viewers. Detect `/XFA` in the AcroForm dict and warn.

## 9. Encryption & permissions

- Standard security handler: **user password** (needed to open) and **owner password** (governs permissions such as print, copy, modify).
- A PDF with only an owner password opens without prompting, but sets permission flags. Respecting permissions is a policy choice; it's not technically enforced. Our editor: show permissions in Properties; warn before editing a restricted file; don't build "remove restrictions" as a feature.
- Algorithms: RC4 40/128 (obsolete), AES-128, **AES-256** (use this when saving with a password).

## 10. Other structures you'll touch

| Structure | What | Editor relevance |
|---|---|---|
| Outline (`/Outlines`) | Bookmarks tree | Show in sidebar; keep consistent after page delete/move (PyMuPDF updates on page ops; verify in tests) |
| Named destinations / links | `/Link` annots with `/Dest` or URI | Preserved on page ops within a doc; `insert_pdf(links=True)` for merges |
| Metadata | `/Info` dict + XMP stream | Properties dialog; sanitize removes both |
| Embedded files | `/EmbeddedFiles` name tree | Show list; remove in sanitize |
| JavaScript | `/JS`, `/OpenAction`, `/AA` | **Never execute.** Strip in sanitize. MuPDF doesn't execute JS by default |
| Optional content (layers, OCG) | Content visible conditionally | Render respects default state; show layers panel (P2) |
| Tagged PDF / structure tree | Accessibility tags | Page ops can break it; note this as a known limitation |
| Linearization | "Fast web view" layout | Lost on incremental save; not important for desktop |
| Page labels | Displayed numbering (i, ii, 1, 2) | Show in page box: "iv (4 of 120)" |

## 11. Glossary

- **xref:** object number of a PDF object. Stable while the object exists, but a deleted-then-recreated object gets a new one, and `garbage` ≥ 2 saves renumber them. Annotations use `/NM` IDs instead (doc 02 §2.2).
- **/NM:** an annotation's "unique name" key. We store our own UUID there as the stable `annot_id`.
- **Quad:** four-point shape (handles rotated/skewed text). Text markup annotations use QuadPoints.
- **Appearance stream (AP):** drawing instructions for an annotation's look.
- **Widget:** the annotation that shows a form field.
- **Base-14:** fonts every viewer must have.
- **Subset font:** embedded font with only the used glyphs.
- **Flatten:** merge annotations/fields into page content.
- **Garbage collection (save):** removing unreferenced objects; `garbage=3` also merges duplicates, `garbage=4` also dedupes streams.
- **Incremental save:** appending changes rather than rewriting.
- **Content stream:** a page's drawing instructions.
- **XObject:** external object: Image XObject or Form XObject (reusable content).
- **CTM:** current transformation matrix in a content stream.
