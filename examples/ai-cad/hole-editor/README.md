# Interactive through-hole workflow

The browser starts with a saved L-shaped extrusion, places two holes, previews/saves, then drags the right hole from x=70 to x=60 mm and increases its radius from 3 to 4 mm. The other center remains (10,50) with radius3. Thickness stays5 mm and feature/hole IDs persist. Exact material volume changes from `12000 − 90π` to `12000 − 125π` mm³.

## Use

Follow [setup](../../../tools/ai-cad/README.md), then copy the example so edits do not change this reference:

```sh
mkdir -p work
cp examples/ai-cad/hole-editor/base.cad.json work/hole-demo.cad.json
python3 tools/ai-cad/viewer.py --store work/hole-demo.cad.json
```

Click **Add through-holes** under the extrusion, place centers in the top-view outline, set radii, preview and save. Use **Edit holes** to move circles or edit exact coordinate/radius fields. **Add at origin** provides a keyboard-accessible starting point; move its center inside before previewing.

## Delivered artifacts

- `base.cad.json`: original no-hole model, revision1.
- `create.cad.json`: two placed holes, revision2.
- `edit.cad.json`: moved/enlarged second hole, revision3. All are editable native documents with history.
- `browser-recording.json`: four actual preview/save requests and replies, including derived display meshes. Captured from browser mouse placement, dragging and radius input; no AI inference in this recording.
- `placement.png`, `solid.png`: actual placement dialog and final saved solid.
- `plate.stl`: final saved revision3, millimeters, 128 inscribed chords per circle. Native constraints/history/exact circles are absent from STL; retain the native document.

`python3 tools/ai-cad/verify_hole_recording.py` replays all commands, compares exact native output and snapshots, checks preview immutability, reopen and undo, and independently measures display/STL topology and volume. `node --test tools/ai-cad/test_hole_editor.mjs` exercises the real Rust engine for valid edits, breakout/overlap/bad radii, shared/fixed/derived parameters, unsupported parents and draft limits. Browser checks also confirmed that an invalid hole leaves the saved file byte-identical and an external height edit causes revision conflict while preserving the draft.

## Limits

One group per profile extrusion, 1..16 separate circular holes, positive-Z full-depth only. The recording predates topology editing; the current editor also adds/removes holes and retains surviving IDs. See [structural editing](../feature-edits/README.md). The document has a separate 64-parameter cap. Placement snaps to1 mm; fields accept integer or fraction strings. Geometry and constraint errors come from Rust, and the dialog retains invalid drafts for correction. Fixed/derived dimensions stay locked; changing a shared parameter affects all its uses, including profile coordinates. Derived values update at preview. General geometric constraints, blind holes, breakouts and arbitrary axes remain unsupported.
