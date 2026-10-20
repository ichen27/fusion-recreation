# Exact decimal and unit dimension entry

Dimension commands accept decimals, integers and fractions with optional mm, cm, m, in or ft. Native model values remain exact rational millimeters. This is input conversion, not a document display-unit preference or a general expression parser. See the [contract](../../../docs/ai-cad-contract.md#exact-dimension-entry) for limits.

The browser creates stock with width `1/2 in`, depth `2.54 cm`, height `.01 m`; saved dimensions are `127/10`, `127/5`, `10`, and volume is `16129/5` mm³. Editing width to `.75 in` gives `381/20` mm and `48387/10` mm³. A rejected `1 yd` entry remains in the input while the saved file stays unchanged. Undo restores the original width. A separate unsaved sketch draft accepts `1 in` and draws at 25.4 mm; its native preview produces `127/5` and is discarded.

The isolated MCP run creates the same mixed-unit stock, measures it, previews and commits a `-1/4 in` adjustment, rejects an unsupported unit and a preserved-dimension change, then undoes the adjustment. These are actual transport calls, not evidence of a new language-model inference session.

| Artifact | Purpose / how to use |
|---|---|
| `browser-source.cad.json` | Synthetic source document for replay; existing shell, mirror, cut and linked copy |
| `browser-created.cad.json`, `browser-edited.cad.json`, `browser-undo.cad.json` | Editable native checkpoints with history; open with the viewer's `--store` argument |
| `browser-download.cad.json` | Actual browser native download, identical to the edited checkpoint |
| `browser-solids.zip` | Actual downloaded STL collection plus manifest; `04-stock1.stl` is the new stock |
| `browser-recording.json` | Fourteen actual preview-job/command requests and replies, including a failed unit preview |
| `browser-audit.json`, `browser-runtime.json` | Retained DOM draft observations and native worker/process measurements |
| `sketch-units.png` | Actual 1280×900 browser screenshot, visually inspected; shared coordinates retain typed units |
| `mcp-created.cad.json`, `mcp-edited.cad.json`, `mcp-undo.cad.json` | Native checkpoints from the isolated MCP session |
| `mcp-recording.json` | Eight actual typed MCP calls and replies |

From the repository root, build the release model engine as documented in the [runtime README](../../../tools/ai-cad/README.md), then run:

```sh
python3 -m unittest discover -s tools/ai-cad -p 'test_dimension_input.py' -v
node --test tools/ai-cad/test_dimension_input.mjs tools/ai-cad/test_hole_editor.mjs
python3 tools/ai-cad/verify_dimensions.py
# In the documented MCP environment:
python tools/ai-cad/verify_dimensions_mcp.py
```

The replay compares saved bytes/state, actual transport replies and independent STL edge-incidence/signed-volume integrals against fractional physical dimensions. It does not rerun the browser or claim new browser measurements in CI. Rust tests cover conversion grammar and budgets; host tests cover fixed/preserved values, tiny decimals, rejection atomicity and strict native model parsing. The sketch/hole drawing helper uses floats only for temporary visualization; original input strings reach Rust without float conversion.
