# Editable project download and undoable import

The browser can download the complete native `.cad.json` document, including parameters, features, relationships, undo/redo history and transaction receipts. A revision check prevents downloading a different saved revision from the one shown.

**Import saved model…** validates a selected native file and previews its current model. **Replace model** saves that model as one undoable edit in the current workspace. The workspace keeps its own revision and transaction history; the source file's history and receipts are not copied. The source file is unchanged. Import supports the same stale-revision rejection and idempotent retries as other edits. No-change imports reject without advancing revision.

To reopen a downloaded project with its complete original history, copy it to a working path and run:

```sh
python3 tools/ai-cad/viewer.py --store work/downloaded.cad.json
```

Build the engine using [setup](../../../tools/ai-cad/README.md) first. Native files are limited to 16 MiB. Every current/undo/redo model is validated before importing; checksum or geometry failures leave the workspace unchanged. This is a single-document workspace, not a project library or multi-user synchronization service. Checksums detect damage; they do not authenticate a file's author.

## Recorded acceptance run

Starting from an empty workspace, import the [browser-created two-part document](../browser-stock/final.cad.json), save, change blind-pocket depth from 4 to 6 mm, undo the dimension edit, undo the import, then redo the import and download. The downloaded revision 5 retains the redo entry for the depth change. Reopen and redo restores depth 6. Selecting a file with a damaged checksum rejects before any replacement.

Run `python3 tools/ai-cad/verify_native_recording.py` to replay the eight actual browser calls and verify the native checkpoints, exact downloaded bytes and reopened history. Unit/HTTP tests also cover replacing an existing model, source-history isolation, malformed historical states, transaction conflict/retry and stale/oversized files.

## Artifacts

- `browser-recording.json`: eight actual browser commands/replies; display mesh and approximate volume omitted. No inference run is claimed.
- `imported.cad.json`, `edited.cad.json`, `undo.cad.json`, `empty.cad.json`: editable revision 1–4 checkpoints.
- `downloaded.cad.json`: actual browser download at revision 5, including undo and redo history.
- `damaged.cad.json`: deliberately invalid checksum fixture, expected to reject.
- `import-preview.png`, `damaged-file.png`: actual browser preview and rejection evidence.

All valid checkpoints can be opened with the viewer. The damaged fixture is intentionally unsuitable as a working document.
