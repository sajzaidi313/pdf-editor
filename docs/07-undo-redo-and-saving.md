# 07: Undo/Redo, Dirty State & Saving

## 1. Requirements

- Every document mutation is undoable (Ctrl+Z) and redoable, including page ops, redaction (until saved), and form fills.
- "Dirty" indicator (`*` in title, prompt on close) is exact: undoing back to the saved state = clean.
- Saving never corrupts the original file, even if the app crashes mid-save.
- Undo history survives a normal Save.

## 2. Options considered

| Approach | How | Pros | Cons |
|---|---|---|---|
| **MuPDF journal** (`doc.journal_*`) | MuPDF records object changes per operation | Exact, low memory | ✅ Verified: `insert_pdf` fails inside an op; *every* mutation must be wrapped in an op once enabled (even internal helper calls); opaque when it fails; ties stack order to MuPDF's |
| **Inverse operations** | Each command knows how to reverse itself | Fast, low memory | Many ops have no cheap inverse (content insertion, redaction, deleting a complex annotation) |
| **Snapshots** | Store `doc.tobytes()` before the op; undo = reload bytes | Works for *everything*, simple, reliable | Memory heavy for big docs; reload cost; invalidates all `Page` objects |

## 3. Decision: hybrid command pattern (inverse where cheap, snapshot otherwise)

```python
# core/commands/base.py
class Command(ABC):
    label: str
    def do(self, m: DocumentModel) -> DocChange: ...
    def undo(self, m: DocumentModel) -> DocChange: ...
    def merge_with(self, other: "Command") -> bool: return False   # for drag/nudge/slider coalescing
    id: int = -1   # same non-negative id → QUndoCommand.mergeWith is consulted

class InverseCommand(Command):
    """Subclasses implement do() and undo() directly."""

class SnapshotCommand(Command):
    """Subclasses implement apply(m). Undo/redo swap whole-document byte snapshots."""
    def __init__(self) -> None:
        self._before: bytes | None = None
        self._after: bytes | None = None

    def do(self, m):
        if self._after is not None:          # redo: restore state after the first apply
            m.restore_snapshot(self._after); return DocChange(ChangeKind.RELOADED)
        self._before = m.doc.tobytes()       # garbage=0 → xref numbers preserved ✅
        try:
            change = self.apply(m)
        except Exception:
            m.restore_snapshot(self._before); raise   # leave doc untouched on failure
        self._after = m.doc.tobytes()
        return change

    def undo(self, m):
        m.restore_snapshot(self._before); return DocChange(ChangeKind.RELOADED)

    @abstractmethod
    def apply(self, m) -> DocChange: ...
```

`DocumentModel.restore_snapshot(data)`: `old = self.doc; self.doc = pymupdf.open(stream=data, filetype="pdf"); old.close(); self.requires_full_save = True`. It does **not** call `notify()`: the command returns `DocChange(ChangeKind.RELOADED)` and `QtCommand` notifies once (doc 02 §3). Note: opened-from-bytes docs have `doc.name == None`, so **the model keeps `self.path` separately** and never relies on `doc.name`.

✅ Verified: `tobytes()` → reopen keeps annotation xrefs identical, so `InverseCommand`s earlier in the stack that hold xrefs still work after a snapshot undo/redo.

### Which command uses which strategy

| Command | Strategy | Undo detail |
|---|---|---|
| AddAnnot (all types) | Inverse | delete by `annot_id`; redo recreates with the **same** `annot_id` |
| ModifyAnnot (color, opacity, border, content, rect) | Inverse | store old props dict, reapply; `update()` |
| MoveAnnot (rect-based) | Inverse | old rect; mergeable for nudges |
| MoveAnnot (vertex-based, recreate) | Snapshot | recreated annot keeps its `annot_id`; snapshot is still the simplest correct undo |
| DeleteAnnot | Snapshot | (reconstructing arbitrary annots from props loses details) |
| RotatePages | Inverse | rotate back |
| ReorderPages | Inverse | `select(inverse_order)` |
| DeletePages / InsertPages / InsertFromFile / Duplicate | Snapshot | |
| SetFieldValue | Inverse | old value; `update()` |
| ApplyRedactions / ReplaceSpan / AddPageText / InsertImage / Signature / Whiteout | Snapshot | |
| Flatten / Scrub / Optimize | Snapshot | |
| SetMetadata | Inverse | old dict |

### Memory control
- Call `QUndoStack.setUndoLimit(100)` right after creating the stack (Qt only allows setting the limit while the stack is empty).
- **The cost, in numbers:** each `SnapshotCommand` holds a "before" *and* an "after" copy of the whole file. On a 50 MB document (the size in the spec's performance target) that's ~100 MB per page delete, so a 500 MB budget only fits ~5 such edits.
- **Share identical snapshots (do this in M4; it's easy).** When two snapshot commands run back-to-back, command N's "after" bytes and command N+1's "before" bytes are the same document. `DocumentModel` keeps one cached snapshot:
  - `model.snapshot_bytes()` returns the cached bytes if the doc hasn't changed since they were taken, otherwise calls `tobytes()` and caches the result.
  - Every `do()`/`undo()` ends with the cache invalidated (`QtCommand` does it), **except** `SnapshotCommand`, which sets the cache to the bytes it just captured or restored.
  - Python `bytes` are immutable, so sharing one object between commands is safe and costs nothing.
  - The render process (doc 05 §3.1) uses the same cached snapshot, so one `tobytes()` serves both undo and rendering.
  - Budget accounting counts each distinct bytes object once (track them by `id()`).
- **Budget and trimming:** track total snapshot bytes held by commands. `QUndoStack` can't drop just its oldest entries, so when the total passes the budget (default 500 MB), clear the stack and show a status-bar notice: "Undo history trimmed to save memory".
  **Watch out:** `QUndoStack.clear()` also marks the stack *clean*, so unsaved work would suddenly look saved (no `*` in the title, no prompt on quit → data loss). Before clearing, check `stack.isClean()`; if it was *not* clean, set `model.unsaved_outside_history = True` (see §6).
- **Later, only if trimming happens too often in real use: spill snapshots to temp files.** Rules if you build it:
  - Files go in a user-only folder in the app data dir (`undo/`), never next to the document.
  - Delete a file as soon as its command is deleted (stack clear, undo limit), on document close, and delete leftovers on startup.
  - **Never spill for documents opened encrypted:** snapshots are decrypted (doc 07 §5.4), so for those keep RAM-only and trim instead.
- For docs > 100 MB, warn once that page-structure edits use more memory.

### History panel
Qt ships a ready-made list view of the undo stack: `QUndoView(stack)`. Put it in a "History" sidebar tab.
- Each row is a command's `label` ("Rotate Page", "Highlight"); clicking a row undoes or redoes everything up to that point. So labels should be short and specific.
- `view.setEmptyLabel("Opened file")` names the starting state; `view.setCleanIcon(...)` can mark the last saved state.
- It's also the best debugging tool for the command system: a missing row means a change bypassed the stack (CLAUDE.md rule 2).
- Jumping far back runs many undos in a row, some of them snapshot restores; that's correct, just possibly slow on big docs. Show a busy cursor while it runs.

### Macros
Multi-page actions (highlight across pages, mark N search results, rotate selection) use `stack.beginMacro(label)` … `endMacro()` so one Ctrl+Z undoes all.

### Merging
Arrow-key nudges, slider drags (opacity), color picker previews: give the command a fixed `id()` and implement `mergeWith` to absorb consecutive commands on the **same `annot_id`**.

## 4. Things that invalidate references

| Event | Page objects | Annot objects | xrefs |
|---|---|---|---|
| Any annotation add/delete | stay valid | others stay valid | stable |
| `delete_page`, `select`, `move_page`, `insert_pdf` | **re-fetch** | re-fetch | stable for surviving objects |
| Snapshot restore | **invalid** | invalid | stable ✅ |
| Save with `garbage` ≤ 1 then reopen | invalid | invalid | stable ✅ |
| Save with `garbage` ≥ 2 then reopen | invalid | invalid | **renumbered** ✅ (verified: an annot went 9 → 7 with garbage=2, → 6 with garbage=3) |

Rule: **never cache `Page`/`Annot` objects across commands.** Store `(page_index, annot_id)` for annotations and `(page_index, xref)` for form widgets, and re-fetch. Annotation IDs live in `/NM`, so they survive every row of the table above, including renumbering saves.

## 5. Saving

### 5.1 Save modes
```python
def save(model: DocumentModel, *, path: Path | None = None, secure: bool = False) -> None:
    target = path or model.path
    if (not secure and path is None and not model.requires_full_save
            and model.opened_from_file and model.doc.can_save_incrementally()):
        model.doc.save(str(target), incremental=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)   # fast path
        return
    tmp = target.with_name(f".{target.name}.saving-{os.getpid()}.tmp")
    garbage = 3 if secure else 1        # 1 keeps xrefs → undo stack survives
    model.doc.save(str(tmp), garbage=garbage, deflate=True, use_objstms=1,
                   **encryption_args(model))   # ⚠ without this, a full save writes the file UNENCRYPTED
    _verify_opens(tmp, model.user_pw)   # open (authenticate if needed), check page_count matches
    model.doc.close()                   # Windows can't replace a file that is open
    os.replace(tmp, target)             # atomic on same filesystem
    model.reopen(target)                # new Document (authenticates with model.user_pw if needed)
    if secure:
        model.undo_stack_clear_requested = True   # xrefs renumbered → inverse commands unsafe


def encryption_args(model: DocumentModel) -> dict:
    """Full saves drop encryption unless we ask for it again (see §5.4)."""
    if not model.keep_encryption:
        return {}                       # pymupdf's default for a full save: no encryption
    return {"encryption": pymupdf.PDF_ENCRYPT_AES_256, "user_pw": model.user_pw,
            "owner_pw": model.owner_pw, "permissions": model.permissions}
```

- **Secure save** is forced after `ApplyRedactions`, `Scrub`, or when the user picks "Save As (sanitized)". It uses `garbage=3`+, which renumbers objects, so the undo stack is cleared with a message ("Redactions are now permanent; undo history cleared").
- ✅ Saving non-incrementally to the doc's own open path raises `"save to original must be incremental"`; that's why we always write a temp file.
- The temp file is in the **same directory** so `os.replace` is atomic (cross-filesystem moves aren't).
- If anything fails before `os.replace`, delete tmp and keep the doc open as-is; show error.
- If `model.doc.close()` succeeded but `os.replace` failed (file locked by another app, e.g. Acrobat on Windows): reopen from tmp bytes, keep tmp, tell the user where it is.
- Preserve file permissions/metadata when replacing: `shutil.copymode(original, tmp)` before replace.

### 5.2 Incremental-save caveats
- Faster and keeps any existing digital signatures intact (the original signed byte range is untouched).
- But incremental saves accumulate: file grows each save, and **old content remains in earlier revisions**. Never use it after redaction or text replacement (C4); both set `requires_full_save`.
- If the file was repaired on open (`doc.is_repaired`), incremental save may be impossible: `can_save_incrementally()` → False → full save.

### 5.3 Save As
Always full save (`garbage=1`, or 3 when "optimize" checked) to temp in target dir → replace → model switches `path` to the new file and reopens from it.

### 5.4 Encrypted docs
Opened with password → saving incrementally keeps encryption (`PDF_ENCRYPT_KEEP`). Full saves must pass encryption explicitly or the output is **decrypted**: carry `user_pw`/`owner_pw` in the model (memory only, never persisted) and pass `encryption=PDF_ENCRYPT_AES_256` via `encryption_args()` (§5.1).
- **Record the encryption state on open** (`keep_encryption`, passwords, `permissions`) in the model. Don't re-check `doc.is_encrypted` later: after a snapshot undo, the doc is reopened from `tobytes()` bytes, which are *decrypted*, so it would wrongly report "not encrypted".
- **Usually you only know one password** (the user typed the user password). Ask once when the first full save happens: "Keep password protection? Owner password: [same as open password] / [enter one]".
- **Owner-only restricted file** (opened without typing a password): we don't know the owner password. Re-apply the same `permissions` with a newly generated random owner password, so a full save keeps the restrictions instead of silently removing them (doc 03 §9: we don't build "remove restrictions").

## 6. Dirty tracking

Use the undo stack as the source of truth, plus one flag for changes the stack has forgotten:
- `is_dirty = (not stack.isClean()) or model.unsaved_outside_history`
- After open and after each successful save: `stack.setClean()` and `model.unsaved_outside_history = False`.
- `stack.cleanChanged(bool)` and changes to the flag → recompute `is_dirty` → update title (`"file.pdf*"`), enable Save action.
- Edge: after a secure save clears the stack, call `setClean()` again.
- Edge: `stack.clear()` while dirty (memory trim, §3) → set `unsaved_outside_history = True` *before* clearing, because `clear()` makes the stack report clean.
- Edge: `setUndoLimit` drops the oldest commands automatically. If the saved state was among them, `isClean()` stays False until the next save; that's correct, nothing to do.
- Changes made outside the stack (should be none) would be invisible; enforce rule 2 in CLAUDE.md.

Close/open-another/quit flow: if not clean → `QMessageBox` Save / Don't Save / Cancel. Hook `closeEvent` of the main window.

## 7. Autosave & crash recovery (P2)

- Every 2 minutes when dirty (and idle ≥ 3 s): write `doc.tobytes()` to `AppDataLocation/recovery/<hash-of-path>.pdf` + a JSON sidecar `{original_path, timestamp}`. Write the bytes to disk on a plain Python thread (fine here because writing bytes doesn't call PyMuPDF; the `tobytes()` call itself must be on the UI thread; it's usually fast enough, else skip for docs > 200 MB).
- **Never write a recovery file for a document that was opened encrypted.** `tobytes()` returns a *decrypted* copy, so the protected content would land on disk in plain form. Show "Autosave is off for password-protected files" in the status bar instead.
- **After redactions are applied but not yet saved** (`model.requires_full_save`), write the recovery file with `doc.tobytes(garbage=3)`, not `garbage=0`: plain snapshots can still contain the removed content.
- Delete recovery files on clean close.
- On startup, if recovery files exist → dialog listing them: "Recover / Discard".

## 8. External modification

Use `QFileSystemWatcher` on the open path. If the file changes on disk and we didn't write it: banner "File changed on disk. Reload (lose unsaved changes) / Keep mine". Ignore events during our own save (flag + compare mtime/size after save).
