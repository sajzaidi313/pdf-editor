# 09: Security, Licensing & Edge Cases

## 1. Threat model (it's a local app, but PDFs are hostile input)

PDFs are a classic malware delivery format. Assume any opened file may be malicious.

| Risk | Mitigation |
|---|---|
| Parser exploits (malformed objects, huge streams, decompression bombs) | Keep PyMuPDF updated: it's pinned to a version range (CLAUDE.md); bump it regularly, since it bundles MuPDF security fixes, and run `tests/pymupdf_behavior` after each bump. Render in a separate process so a hang or crash doesn't take down the UI; on a per-page timeout, kill and restart the process and show a "page too complex" placeholder |
| Embedded JavaScript | **Never execute.** MuPDF doesn't run JS by default; don't enable it. Show a "contains JavaScript (not run)" info badge |
| Launch actions / URI actions | Never auto-follow on open. Links open only on user click, with confirmation showing the full URL. Only `http`/`https`/`mailto` are ever opened (`file:`, `javascript:` etc. are refused; doc 05 §9). Never execute `/Launch` actions |
| Embedded files (attachments) | List them; "Save attachment as…" only with explicit user action; never open/execute them |
| Resource exhaustion (100k pages, 30,000×30,000 pt page, huge images) | Cap render pixel size (tiling, doc 05 §4); cap page-count-dependent UI work (lazy thumbnails); handle `MemoryError` → friendly message |
| Remote content (XFA/external refs) | No network code anywhere. Don't fetch external URLs |
| Data leakage after "redaction" | Redaction always applied for real + secure full save (doc 06 §R, doc 07 §5); sanitize option for metadata/hidden text; never offer "black box" without the word "cover" |
| Incremental-save leakage | Old revisions remain in incrementally saved files. Offer "Save a clean copy" which does a full `garbage=3` save |
| Temp files containing sensitive data | Recovery snapshots in user-only app data dir; delete on clean exit; **never written for encrypted docs** (they'd be decrypted); written with `garbage=3` after redactions; undo snapshots spilled to disk (if ever built) follow the same rules and are deleted with their commands; tmp save files in the same folder are removed on failure |
| Passwords | Hold only in memory for the session; never write to settings/logs. Redact from exception messages |
| Logs | Never log document text or field values; log paths only at DEBUG |

## 2. Licensing (important if this goes on a resume/GitHub, critical if ever sold)

| Component | License | Implication |
|---|---|---|
| PyMuPDF / MuPDF | **AGPL-3.0** or commercial (Artifex) | Distributing the app (or offering it over a network) requires releasing **your full source under AGPL-compatible terms**. A public GitHub repo under AGPL-3.0 satisfies this. Closed-source/commercial distribution → buy a commercial license or switch engines |
| PySide6 / Qt | LGPL-3.0 (or commercial) | OK for closed or open apps if dynamically linked (PyInstaller one-folder mode keeps Qt libs as separate files). Include LGPL notice; users must be able to replace Qt libs |
| pypdf (tests) | BSD-3 | Fine |
| Bundled fonts (Noto, DejaVu) | SIL OFL / permissive | Include license texts in `resources/fonts/` |
| Icons | choose MIT/Apache sets (e.g. Lucide, Tabler) | Include attribution |
| Tesseract (optional OCR) | Apache-2.0 | Fine; don't bundle language data you don't need |

**Recommendation:** license this project **AGPL-3.0** and put a `LICENSE` file + a "Third-party licenses" dialog (Help → About → Licenses) listing the above.

Permissive escape hatch (if ever needed): rendering with **pypdfium2** (Apache-2.0/BSD-3), editing with **pikepdf** (MPL-2.0, wraps qpdf) + **pypdf** (BSD). Expect to write much more code yourself (annotation appearance streams, redaction text removal is hard without MuPDF). Keep `core/` behind small interfaces so a swap is possible, but don't build an abstraction layer for it now.

## 3. Edge-case catalog (handle or at least fail gracefully)

### Opening
- Zero-byte file, non-PDF with .pdf extension, HTML error page saved as .pdf → friendly "not a valid PDF".
- PDF that opens but `page_count == 0` → show message, disable editing.
- Repaired on open (`doc.is_repaired`) → banner; recommend Save As.
- Password-protected → prompt with retry (3 attempts then cancel); owner-only restrictions → read-only banner + "Edit anyway" (user's own responsibility; log nothing).
- Non-PDF formats MuPDF can open (XPS, EPUB, images) → either refuse, or offer "Convert to PDF" (`pymupdf.open(path).convert_to_pdf()` → bytes → open as PDF). P2.
- Path with unicode/emoji, network drive, very long path (Windows 260 chars) → use `pathlib`, test with unicode fixture name.
- File locked by another program (Windows) → reading usually works; saving in place fails → offer Save As.
- Same file opened twice → focus existing window (single document per window in v1).

### Pages
- Mixed page sizes and orientations → layout centers each page; fit-width uses max width.
- Pages with `/Rotate` not a multiple of 90 (invalid) → MuPDF normalizes; test.
- Huge pages (architectural drawings 36×48 in) → tiling path.
- Thousands of pages → lazy everything; thumbnails virtualized.
- Deleting all pages → disallow (PDF must have ≥ 1 page).

### Text
- No text layer (scans) → selection/highlight disabled with hint "No selectable text; run OCR (if available) or use a rectangle".
- Text in Type 3 fonts or without ToUnicode → extraction garbage → search fails; nothing to do except OCR.
- RTL (Arabic/Hebrew) and vertical CJK → extraction order may be odd; selection imperfect; document as known limitation.
- Ligatures (ﬁ, ﬂ) → search for "fi" may miss; consider `TEXT_PRESERVE_LIGATURES` off (default expands them).
- Invisible text (render mode 3, e.g. OCR layers) → selectable but not visible; redaction must also remove it (`PDF_REDACT_TEXT_REMOVE` handles all; `scrub(hidden_text=True)` for the rest).

### Annotations
- Annotations without appearance streams (made by sloppy tools) → MuPDF synthesizes some; if not, they're invisible. Calling `annot.update()` on them regenerates.
- Annotations with `Hidden`/`NoView` flags → don't show; show in list as hidden.
- Locked annotations (`PDF_ANNOT_IS_LOCKED`) → no move/resize; allow delete only with confirmation.
- Replies (IRT chains) → show as thread in annotation list (P2); deleting parent should ask about replies.

### Forms
- Field names with dots (hierarchy) and duplicate names across widgets (shared value) → treat by `field_name`, update all widgets.
- Checkbox on-state not "On" → always use `on_state()`.
- Fields with format/calc JS → values not recalculated; banner.
- Fonts in DA string not available → PyMuPDF falls back to Helv; non-Latin input may render as `?` → warn when input has non-Latin and field font is base-14.

### Saving
- Disk full / permission denied → error, original untouched (temp-file strategy).
- Target is read-only → offer Save As.
- Saving encrypted doc with full save → must re-apply encryption explicitly (doc 07 §5.4).
- File has digital signatures → warn: "Edits will invalidate existing digital signatures". Detect: any widget with `field_type == PDF_WIDGET_TYPE_SIGNATURE` and `is_signed`.

## 4. Privacy

- No telemetry, no network, no update checks (or explicit opt-in only if ever added).
- Recent files list can be cleared (File → Recent → Clear); this also clears remembered reading positions (V13).
- Saved signatures stored locally; "Delete all saved signatures" button.
