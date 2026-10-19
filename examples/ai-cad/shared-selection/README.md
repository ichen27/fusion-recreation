# Shared saved-body selection

Selecting a saved solid in the browser now publishes its stable feature ID for the read-only `cad_context` MCP tool. The context includes the exact selected body, editable model and one locked revision, so “this part” can refer to an explicit selection. Context is input to planning; it does not authorize an edit.

The workspace sidecar binds selection to both revision and a hash of the complete saved state. Any model edit, undo or replacement with different content invalidates it, even if the same body ID survives. Stale context returns no selected body. Reselecting explicitly acknowledges the current saved model. Previews remain local and never publish candidate geometry as a saved selection.

## Verified browser/MCP sequence

1. Open the included `initial.cad.json` copy at revision 6 and select `intersection1`: MCP reads exact volume 4000 mm³.
2. Through real MCP transport, preview and commit changing `turn1` from 90° to 180°. The browser refreshes to revision 7; context reports stale and returns no selected body.
3. Reselect the saved intersection: MCP now reads 8000 mm³ at revision 7.
4. Clear selection: MCP reports empty. Selection clicks have not changed native model bytes, revision, undo or receipts.

```sh
python3 tools/ai-cad/verify_selection_recording.py
# Real stdio schema/context regression, after mcp-requirements.txt setup:
python tools/ai-cad/verify_mcp.py
```

`browser-recording.json` contains three actual selection requests. `edit-mcp.json`, `reselected-mcp.json` and `cleared-mcp.json` contain real MCP tool requests and replies. No inference run is claimed. `initial.cad.json` and `edited.cad.json` preserve editable checkpoints. `selected.png` and `stale.png` show the actual browser states. Geometry exports for this same rotation/intersection workflow are in [quarter-turn](../quarter-turn/README.md).

## Workspace semantics and limits

- One shared selected body per native document path, with latest successful selection winning across browser tabs. Requests within one browser are queued in click order.
- `<document>.selection.json` is a disposable local workspace file; it is excluded from native export and model history. It survives client restarts while the saved state still matches. Copying a native file does not copy selection.
- Selection writes use the document lock and atomic file replacement. Invalid/stale picks leave the previous context intact. A damaged sidecar reports a context error and can be replaced by Clear selection or a valid pick; model editing remains available.
- `/api/context` reads and `/api/selection` writes follow the viewer's loopback host/origin checks. Selection requests and sidecars are bounded to 4096 bytes.
- The MCP client must restart to discover `cad_context`. No existing client configuration or user design was changed by this work.
- Body-level approximate viewport picking is supported; exact face/edge selection, persistent generated topology references, multi-user presence and selection-specific edit guards remain open. `expected_revision` protects model edits; selection alone never chooses operations or changes parameter preservation rules.
