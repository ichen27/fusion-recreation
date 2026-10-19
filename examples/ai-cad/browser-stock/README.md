# From an empty browser document to two editable parts

This acceptance run starts with no model file. The browser creates a 40×30×20 mm block, keeps `x+z≤40`, then creates circular stock at (70,0), radius 20 mm and height 10 mm. A radius-5 blind pocket of depth 4 mm leaves a 6 mm floor in the circular part. The saved bodies have exact volumes 18000 and 3900π mm³.

An invalid negative height rejects without changing either part. Undo removes the pocket; redo restores it. The final browser download is one ZIP containing both saved bodies, with a revision/units/precision manifest.

## Run

Build using [setup](../../../tools/ai-cad/README.md), then:

```sh
python3 tools/ai-cad/viewer.py --store work/new-part.cad.json
```

Select **New block or circular stock**. Enter the dimensions above, preview, and save. Use **Cut with plane** on the block and **Add holes** on the circle. To open the delivered editable result directly, point the viewer at a copy of `final.cad.json`. Run `python3 tools/ai-cad/verify_stock_recording.py` to replay the recorded workflow.

## Artifacts

- `browser-recording.json`: eleven actual preview/commit/undo/redo calls from the empty document. Display mesh and approximate volume fields are omitted from recorded replies. No AI inference run is claimed.
- `cut.cad.json`, `parts.cad.json`, `undo.cad.json`, `final.cad.json`: editable native history checkpoints, verified by replay and reopen.
- `create-block.png`, `create-round.png`, `parts.png`: actual browser stock forms and final two-part scene.
- `parts.zip`: actual browser download at revision 6, containing `01-holes1.stl`, `02-plane1.stl` and `manifest.json`. The manifest records mm units, exact source volumes, triangle counts and maximum radial chord error. Circle tessellation uses 128 segments. STL does not retain native features or history.

The replay verifier audits closed STL topology, volume and manifest contents. Additional tests interleave a real model commit during archive construction and confirm both exported parts still use the original revision. Filenames have numeric prefixes so case-distinct feature IDs remain distinct on case-insensitive filesystems. Archives have a 64 MiB uncompressed STL limit; larger exports must select bodies individually. A failed body export returns no partial archive.

This is a multi-body document, not an assembly with joints or transforms. The original block remains origin-aligned; circular stock supports an XY center. Geometry limits from the [contract](../../../docs/ai-cad-contract.md) still apply.
