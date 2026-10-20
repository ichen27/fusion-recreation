# Modelling alpha acceptance artifacts

Follow the [alpha guide](../../../docs/modelling-alpha.md) for setup and supported workflows.

Each part directory contains `source.cad.json`, `edited.cad.json`, `reopened.cad.json` (after undo/redo), the complete actual MCP request/reply recording, a closed STL mesh, a STEP solid and an SVG reference sheet. Native JSON files are editable sources; STL/SVG are exports. Copy native files before modifying them. Reference sheets are not manufacturing drawings.

The verification runs three workflows and 29 actual MCP calls. It checks exact volume, preview immutability, saved reopen, stale/invalid edit rejection, undo/redo, reference preservation and connected meshes. `verification.json` records the results. These are deterministic transport and geometry tests; they are not a broad language-model reasoning benchmark.

Reproduce with the pinned MCP Python environment:

```sh
python tools/ai-cad/verify_modelling_alpha.py
# Regenerate the deliverables intentionally:
python tools/ai-cad/verify_modelling_alpha.py --write
```

The rectangular-plate browser screenshot shows a separate interactive 140 × 60 × 6 mm edit (50,400 mm³); its MCP sample is 120 × 60 × 6 mm. Browser evidence also exercises a rejected collapsed rectangle and named reference creation/reselection/removal.

`step-verification.json` records reimported valid single solids and volume agreement within 1e-6 mm³. Reproduce with `python tools/ai-cad/verify_alpha_step.py` in the STEP adapter environment; `--write` regenerates the STEP artifacts.

`browser-recording.json` retains 24 actual browser requests and their immediate replies, including async-preview acknowledgements. `verify_alpha_browser.py` re-evaluates those preview commands synchronously, checks the rejected zero-width draft, compares saved replies and all seven saves/imports, verifies the final native document and the selected shoulder at offset 3 mm. The browser screenshots were visually inspected.
