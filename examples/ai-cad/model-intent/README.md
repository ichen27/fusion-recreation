# Model intent and edit-impact explanations

**Explain solid** and the read-only MCP `cad_explain(expected_revision, feature_id)` use the original Rust engine to identify a feature's sources, controlling parameters and potential edit impact. The graph follows explicit typed references; it does not infer intent from names or substitute a language-model guess.

Each explanation includes:

- Source feature links, direct parameter references, downstream feature IDs and whether the target is a terminal body.
- Exact parameter values, fixed values and affine relationship definitions.
- Root driving parameters for derived values; fixed drivers remain marked as fixed.
- Potentially affected parameters, features and terminal bodies across the entire model, including bodies outside the selected source chain.

Dependency reachability is conservative. It does not prove a proposed numerical edit changes geometry, preserves constraints or succeeds. Preview remains authoritative. It also does not measure degrees of freedom or infer a manufacturing purpose.

## Verified workflow

Two blocks share depth and fixed height. The second uses `half = width/2` and is translated away from the first. Select the positioned body and explain it: only `second` and `positioned` are its source features, but the `width` driver potentially affects both visible solids. Change width from 20 to 40 mm through the browser. Volumes change from 800/400 to 1600/800 mm³; half-width follows from 10 to 20 mm while height stays 5 mm.

```sh
python3 tools/ai-cad/verify_intent_recording.py
# Real MCP transport, after requirements.lock installation:
python tools/ai-cad/verify_mcp.py
```

The Rust `--explain` interface accepts `{model,feature_id}` and validates the entire bounded model before reporting dependencies. HTTP `/api/explain` accepts `{expected_revision,feature_id}` under the same loopback host/origin policy. Native state is locked while selecting the snapshot, and exact explanations use the bounded executable/model cache. No model bytes, history, receipts or selection are changed.

## Artifacts

- `create.json`: reproducible typed fixture creation.
- `initial.cad.json`, `edited.cad.json`: editable native history checkpoints.
- `browser-recording.json`: four actual requests—explain, preview width edit, commit, explain again. Disposable display meshes/approximate volumes omitted.
- `mcp-recording.json`: actual terminal/retained feature explanations and a stale-revision error through stdio MCP. No inference run is claimed.
- `explanation.png`, `impact-detail.png`: actual browser source/parameter/impact views before and after the edit.

Tests also cover chained relations, shared profiles feeding multiple bodies, fixed upstream drivers, holes/depths, literal plane normals, transformations, retained features, missing features, malformed models, cache repeatability and unchanged native files. Adding a Rust feature requires updating the exhaustive reference match. Restart existing MCP clients to discover the additional tool.
