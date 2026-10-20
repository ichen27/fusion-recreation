# Original CAD modelling alpha

This alpha creates and edits bounded mechanical parts using the original Rust kernel. The browser and connected AI client share the same parameter model, preview validation, saved revisions and undo history. Exact geometry runs on the host CPU; WebGL2 on the client GPU draws a disposable mesh.

## Start modelling

The retained [macOS Apple Silicon runtime](../examples/ai-cad/runtime-bundle/README.md) includes the compiled engine, browser host and three alpha samples. It requires Python 3.14+ and a WebGL2 browser. Extract it and follow its `README.md`; no Rust compiler is needed to run the bundle. The archive manifest identifies the source commit and file hashes. This is a development alpha, not a signed installer or a licensed public release; the repository's project license is still undecided.

From a source checkout with Rust 1.85.1 and Python 3.9+:

```sh
cargo +1.85.1 build --release --locked --manifest-path crates/model-engine/Cargo.toml
mkdir -p work
python3 tools/ai-cad/viewer.py --store work/my-first-part.cad.json
```

Open `http://127.0.0.1:8765`. A new path starts an empty workspace. Existing native files reopen with editable features and history. The server binds loopback; see the [host/remote-client setup](../tools/ai-cad/README.md) for forwarding the same port from another machine.

1. **New sketch / solid → Constrained rectangle** creates an outline at the XY origin. Set its width, depth and extrusion height. Preview, inspect the model, then **Save edit**.
2. Use **Edit sketch** to change its driving width/depth. The four corners retain their relationships. Derived coordinate fields are read-only; a zero width is rejected and leaves the draft available to repair.
3. Select the solid and use its modelling actions to add holes, move/copy it or inspect surfaces. Preview every change before saving. Use **Undo** and **Redo** to traverse saved edits.
4. **Download editable project** preserves native intent and history. **Download saved STL** produces a mesh for supported solids. Reference sheets are SVG geometry views, not manufacturing drawings. Optional STEP adapters need the dependencies documented in the source quickstart.

## Three complete examples

Copy an example to `work/` before editing it, or use **Import saved model…** to preview importing it as one undoable edit. Imports preserve the destination's history; they do not copy the source's history.

| Part | Editable native file | Tested change | Export |
| --- | --- | --- | --- |
| Rectangular plate | [100 × 60 × 6 source](../examples/ai-cad/modelling-alpha/rectangular-plate/source.cad.json), [120 mm wide](../examples/ai-cad/modelling-alpha/rectangular-plate/edited.cad.json) | Width changes; depth and fixed thickness remain. Corners follow the width. | [STL](../examples/ai-cad/modelling-alpha/rectangular-plate/edited.stl), [SVG](../examples/ai-cad/modelling-alpha/rectangular-plate/edited.svg), [STEP](../examples/ai-cad/modelling-alpha/rectangular-plate/edited.step) |
| Counterbored mount | [Source](../examples/ai-cad/modelling-alpha/counterbored-mount/source.cad.json), [deeper recesses](../examples/ai-cad/modelling-alpha/counterbored-mount/edited.cad.json) | Recess depth 2 → 3 mm; named shoulder and rim resolve to the new geometry. | [STL](../examples/ai-cad/modelling-alpha/counterbored-mount/edited.stl), [SVG](../examples/ai-cad/modelling-alpha/counterbored-mount/edited.svg), [STEP](../examples/ai-cad/modelling-alpha/counterbored-mount/edited.step) |
| Turned spacer | [Source](../examples/ai-cad/modelling-alpha/turned-spacer/source.cad.json), [longer spacer](../examples/ai-cad/modelling-alpha/turned-spacer/edited.cad.json) | Length 12 → 15 mm; inner/outer radii remain 3/10 mm. | [STL](../examples/ai-cad/modelling-alpha/turned-spacer/edited.stl), [SVG](../examples/ai-cad/modelling-alpha/turned-spacer/edited.svg), [STEP](../examples/ai-cad/modelling-alpha/turned-spacer/edited.step) |

The examples include actual MCP request/reply recordings and native snapshots after undo/redo. [Acceptance results](../examples/ai-cad/modelling-alpha/verification.json) record exact volumes and closed mesh checks. They exercise typed agent commands; they do not measure how reliably an arbitrary language model translates every possible prompt.

## AI workflow

Connect a user-operated MCP client to the same native document as the viewer using the [existing setup](../tools/ai-cad/README.md#connect-your-subscription-client). Restart the connection after updating schemas. This alpha has no embedded chat or inference service.

Example requests for the included parts:

- “Inspect the plate. Make it 20 mm wider; keep its depth and thickness. Preview the parameter edit, then save.”
- “Deepen the mount's counterbores to 3 mm. Keep their radii and stock thickness. Verify the saved seat and rim references still resolve.”
- “Lengthen the spacer to 15 mm without changing either radius. Preview, save and inspect the result.”

The agent must inspect current dimensions and feature intent, use the current revision and shared selection guard when applicable, and handle unsupported geometry explicitly. The kernel enforces geometry and declared constraints; it cannot prove that the user's unstated design intent was understood.

## Named references

**Named references** saves a surface, or one connected edge chain at the intersection of two authored surfaces. Existing saved surfaces can be reselected. Names follow dimension edits on supported analytic bodies, including counterbores and linked instances. The evaluated response provides current face IDs/edge indices.

A reference also records its feature ancestry. Reordering/replacing source structure, removing its surface, or consuming its terminal body rejects the edit. Explicitly remove it or rebind it after the structural operations in the same transaction. Do not simply drop a failed reference to force an unrelated edit through. Generated Boolean/cut face indices are intentionally unsupported. This is conservative reference preservation, not a general solution to persistent topology naming. At most 16 names may be saved.

## Alpha limits and next gates

The supported envelope includes planar sketches/extrusions, directed affine and exact linear dimension constraints, analytic round stock, supported holes/revolutions, bounded planar Booleans, supported placements, materials, mass properties and geometry inspection. See the command contract for each operation's limits.

General nonlinear sketch solving, arbitrary curved Booleans, freeform surfaces, generic fillets, arbitrary-axis transforms, assembly joints, CAM and collaborative editing are not complete. The feature/parameter budgets remain 32/64. Physical power-loss recovery and compatibility across all OS versions are not certified. Unsupported operations fail explicitly; no mesh or OCCT modelling fallback is substituted.

Next gates are wider real-part acceptance testing, generated-face reference tracking, broader sketch constraints, curved-operation robustness, installers and a project licensing decision. The [platform delivery plan](platform-delivery-plan.md) remains the long-term roadmap.

## Reproduce validation

```sh
cargo +1.85.1 test --release --locked --manifest-path crates/model-engine/Cargo.toml
python3 -m unittest discover -s tools/ai-cad -p 'test_*.py' -q
node --test tools/ai-cad/test_*.mjs
# In the pinned MCP environment described in the setup guide:
python tools/ai-cad/verify_modelling_alpha.py
```

`--write` on the alpha verifier regenerates the retained native stages, actual MCP recordings, STL and SVG artifacts. It operates on temporary documents and does not touch a configured personal model.
