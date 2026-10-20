# Revision-bound parts inventory

Open [source.cad.json](source.cad.json) in the viewer and choose **Parts inventory**.
The source has a plate, its linked copy, a differently shaped equal-volume block,
and a cylindrical solid. Three bodies have saved uniform materials; one is unassigned.
Every terminal solid remains a separate row, including equal-volume shapes and copies.

## Run and verify

Build the engine and install the optional MCP lock as described in the
[host quickstart](../../../tools/ai-cad/README.md). From the repository root:

```sh
python3 tools/ai-cad/viewer.py --store examples/ai-cad/inventory/source.cad.json
python3 tools/ai-cad/inventory.py --store examples/ai-cad/inventory/source.cad.json --revision 1 --format csv
python3 tools/ai-cad/verify_inventory.py
.venv/bin/python tools/ai-cad/verify_inventory_mcp.py
```

Copy the sample to your workspace before editing it. The viewer also downloads JSON
with exact values and material provenance. Import CSV exact-number columns as text;
spreadsheet auto-conversion can turn rational strings into dates. Formula-like names
receive an apostrophe prefix in CSV; JSON preserves their original spelling.

## Retained deliverables

| File | Purpose |
| --- | --- |
| [source.cad.json](source.cad.json), [edited.cad.json](edited.cad.json), [undo.cad.json](undo.cad.json) | Editable native history; plate height2→3→undo, with linked-copy rebuild |
| [source.json](source.json), [source.csv](source.csv) | Four source rows; volumes80,80,80 and18*pi mm³ |
| [edited.json](edited.json), [edited.csv](edited.csv) | Plate/copy volumes120 mm³; independent bodies unchanged |
| [mcp-recording.json](mcp-recording.json) | Nine actual stdio calls, preview isolation, stale read rejection, edit and undo |
| [browser-recording.json](browser-recording.json), [browser-audit.json](browser-audit.json) | Seven actual HTTP inventory reads; source exports, stale rejection and recovery |
| [browser-source.json](browser-source.json), [browser-source.csv](browser-source.csv), [browser-edited.json](browser-edited.json) | Actual browser downloads, byte-matching their command-line counterparts |
| [browser.png](browser.png) | Inspected desktop inventory view |

The source-model SHA256 changes after the height edit and returns to its original
value after undo, even though the document revision keeps increasing. Preview and
inventory reads leave native bytes unchanged. Exports recheck the saved revision.

This is a **flat body inventory**, not a manufacturing bill of materials. It has no
part numbers, assembly hierarchy, purchasing data or inferred equivalence groups.
A pattern or disconnected body is one row/quantity1, not a count of its pieces.
Consumed features and standalone profiles are excluded. Spatial overlap does not
merge rows. Material conflicts and missing assignments remain explicit.

The earlier retained runtime archive is pinned to its own source commit and does not
include this new feature. Build a new runtime from this revision to package it.
