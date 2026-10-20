# AI-native CAD: first editable workflow

A bounded working slice of an original CAD engine. A signed-in Codex or Claude Code client can use typed MCP tools to inspect and change a local editable model. The same document is visible and editable in a WebGL 2 browser viewer. Geometry is computed by our Rust boundary kernel, with no OCCT modeling fallback.

**Status:** working model/command contract and tested MCP transport, not a general CAD product. Natural-language reasoning happens in the connected agent client. The viewer has dimension controls, not an embedded AI chat. A live two-turn Codex conversation using ChatGPT sign-in has now created and widened the part through MCP. [Recording, editable snapshots and replay check](../../examples/ai-cad/live-codex/README.md) are included. Claude Code remains transport-compatible but has not been tested with an authenticated session.

## Quickstart

Requires macOS/Linux, Python 3.14, Rust 1.85.1 with Cargo, and a WebGL 2 browser. Run from the repository root. Store your own documents outside the repository (or in ignored `work/`). This host uses POSIX file locks and is not yet supported on Windows.

```sh
cargo +1.85.1 build --manifest-path crates/model-engine/Cargo.toml --release --locked
mkdir -p work
python3 tools/ai-cad/cad.py --store work/demo.cad.json < examples/ai-cad/create.json
python3 tools/ai-cad/cad.py --store work/demo.cad.json < examples/ai-cad/widen.json
python3 tools/ai-cad/viewer.py --store work/demo.cad.json
```

Open http://127.0.0.1:8765. You should see width 120, depth 60, thickness 12, corner setback 10, and exact volume **85,800 mm³**. Repeating the two fixture commands returns their receipts without applying them twice. Use a new document path to start an independent demo.

The viewer can change unlocked dimensions, preview/save, discard, undo, redo, orbit and zoom. It polls for other clients' saved changes, but retains pending form edits/previews and reports revision conflicts. Decimal input is currently expressed as a fraction (`25/2`, not `12.5`). Volume display is rounded; the exact value is in the tooltip and tool result.

To view a mini-hosted service on another computer, forward the loopback port with SSH and open the forwarded URL. Use the same local/remote port (8765) because the host checks its Host/Origin headers. The HTTP server is a local development viewer, not an internet service. It binds only to 127.0.0.1 and has no account system.

## Editable profile → solid

The [profile extrusion example](../../examples/ai-cad/profile-extrusion/README.md) creates a five-sided XY outline, extrudes it 12 mm, then increases width from 100 to 120 mm. Exact volume changes from **57000 to 68400 mm³**. Named coordinates and fixed thickness remain editable in the same document workflow.

```sh
python3 tools/ai-cad/cad.py --store work/profile.cad.json < examples/ai-cad/profile-extrusion/profile.json
python3 tools/ai-cad/cad.py --store work/profile.cad.json < examples/ai-cad/profile-extrusion/extrude.json
python3 tools/ai-cad/cad.py --store work/profile.cad.json < examples/ai-cad/profile-extrusion/widen.json
python3 tools/ai-cad/viewer.py --store work/profile.cad.json
```

Run the viewer after the first command to see the unextruded outline. It can edit coordinate parameters, preview rebuilt geometry, save and undo. The viewer can create simple planar profiles/extrusions with **New sketch → solid**, and edit existing profile coordinates with **Edit sketch**. Through, blind and counterbored holes can be placed with **Add holes** on an extrusion/cylinder or adjusted with **Edit holes** on a group. The hole editor exposes shared recess depth/radius for counterbores. Restart connected MCP clients after upgrading to load the new typed feature schemas.

## Preserve design relationships

[The symmetric-profile example](../../examples/ai-cad/relationships/README.md) adds `tip_x = width / 2`. Increasing width from 100 to 120 mm moves the tip from 50 to 60 mm automatically; thickness remains fixed. The browser shows derived dimensions and their formulas. CLI/MCP can create, replace or remove the rules.

```sh
python3 tools/ai-cad/cad.py --store work/related.cad.json < examples/ai-cad/relationships/create.json
python3 tools/ai-cad/cad.py --store work/related.cad.json < examples/ai-cad/relationships/widen.json
python3 tools/ai-cad/viewer.py --store work/related.cad.json
```

Rules support exact affine combinations of existing parameters, not a general sketch solver. Cycles, direct edits of derived values, fixed/preserve conflicts and invalid rebuilt geometry fail atomically. See the [contract](../../docs/ai-cad-contract.md#exact-parameter-relationships).

## Connect your subscription client

Install the optional MCP adapter into an isolated environment on the computation host:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r tools/ai-cad/requirements.lock
```

In your agent client's MCP settings, register a **stdio** server:

```json
{
  "command": "/absolute/path/to/repository/.venv/bin/python",
  "args": [
    "/absolute/path/to/repository/tools/ai-cad/mcp_server.py",
    "--store",
    "/absolute/path/to/repository/work/my-part.cad.json"
  ]
}
```

For the Codex CLI, the equivalent registration is:

```sh
codex mcp add original-cad -- /absolute/path/to/repository/.venv/bin/python /absolute/path/to/repository/tools/ai-cad/mcp_server.py --store /absolute/path/to/working-part.cad.json
codex mcp get original-cad
```

Start a new Codex session after registration so the tools are loaded. Ask it to use `original-cad`; the configuration entry is named with a hyphen, and clients may normalize tool names. To remove the connection, run `codex mcp remove original-cad` (the CAD document remains on disk).

Use absolute paths and choose the same document for viewer and MCP. The store path is host configuration; the model cannot request arbitrary paths through the CAD tools. For a client on another computer, launch this exact command over your existing SSH connection to the computation host. Python, the Rust binary and the document must all be on that host.

With Codex signed in through an eligible ChatGPT plan, the agent uses subscription access. Claude Code also supports signing in with a Claude subscription and using MCP tools. The CAD server does not read or forward provider credentials. Plan limits still apply. This is a user-operated agent workflow; embedding inference inside a distributed app is a separate product/authentication decision.

Verified references, 2026-10-15: [Codex authentication](https://learn.chatgpt.com/docs/auth), [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli), [Claude Code MCP](https://code.claude.com/docs/en/mcp), [Claude authentication/integration rules](https://code.claude.com/docs/en/legal-and-compliance). Anthropic directs developers embedding Claude capabilities in their own products to API authentication, and disallows collecting/intermediating Claude subscription credentials.

Start with an empty document and say:

> Use the CAD tools to create a 100 × 60 × 12 mm block. Cut the +X/+Y vertical corner with a 10 mm setback along each adjacent edge. Fix thickness and corner size. Inspect, preview, then commit the model.

Then:

> Make that block 20 mm wider while preserving depth, thickness and corner-cut size. Edit its width parameter, preview and commit.

Tools: `cad_inspect`, `cad_preview`, `cad_commit`, `cad_history`. The adapter gives the agent typed operation schemas, supported-geometry descriptions, exact measurements and structured errors. No prompts are sent to an AI provider by this server itself.

## Contract

See [the full command contract](../../docs/ai-cad-contract.md). CLI requests are JSON on stdin; one JSON reply is written to stdout. Errors use `{ "error": { "code", "entity", "message" } }`. Successful replies have a `result` with revision, editable model, exact boundary, volume and changed parameter IDs.

- Model: named exact rational parameters in mm, optional affine relationships, ordered features, explicit fixed-value constraints.
- Features: origin-aligned block; one equal-setback vertical +X/+Y corner cut referencing an earlier block. Terminal solids and unextruded profiles are displayed. Also: simple concave or strictly convex XY polygon profiles with named parameter-backed vertices and positive-Z extrusion. Independent bodies can overlap; their volumes are per-body, not a union volume.
- Operations: define/set/adjust parameter, set/remove relationship, add feature, fix/release parameter. Constraints must be explicitly released to change them.
- Preview and commit take an expected revision and a list of parameter IDs to preserve. The whole proposed model must pass Rust validation.
- Atomic snapshots retain 64 undo/redo steps and up to 1024 transaction receipts. Revision increases for undo/redo. Receipt exhaustion fails explicitly; there is no silent idempotency expiry.
- Stable feature/parameter IDs are supported. Boundary face/edge array indices are **not** persistent topology names.

## Validation and artifacts

```sh
cargo +1.85.1 fmt --manifest-path crates/model-engine/Cargo.toml --check
cargo +1.85.1 clippy --manifest-path crates/model-engine/Cargo.toml --locked --all-targets -- -D warnings
python3 -m unittest discover -s tools/ai-cad -p 'test_*.py' -v
.venv/bin/python tools/ai-cad/verify_mcp.py
python3 tools/ai-cad/verify_codex_recording.py
python3 tools/ai-cad/verify_profile_example.py
python3 tools/ai-cad/verify_relationship_example.py
python3 scripts/check.py
```

[Example artifacts](../../examples/ai-cad/README.md) contain both commands, actual JSON results, a reopenable document and a screenshot. The integration tests exercise the compiled Rust engine, constraints, undo/reopen, exact retry receipts, failed saves and competing processes. The stdio test uses the official MCP client; it does not consume model inference. The separate live Codex recording documents one authenticated natural-language run; its replay check validates those accepted commands without repeating inference. CI repeats the contract tests on Linux.

[Profile extrusion validation and limits](../../docs/profile-extrusion-validation.md) records the new geometry and browser checks.

[Relationship validation and measured host latency](../../docs/parameter-relationship-validation.md) records dependency checks and the initial performance baseline.

## Architecture and limits

`crates/model-engine` owns model interpretation and exact geometry; it currently imports the bounded research crate in `experiments/2026-10-15-rust-boundary`. `store.py` owns revisions, locking, receipts, undo and atomic file publication. CLI, MCP and browser share that host. Moving kernel code to a maintained production crate remains future work.

The CPU performs exact rational geometry and validation. The client browser submits float display triangles/edges to WebGL 2. Those triangles are a disposable display cache; the saved model remains parametric and exact. No GPU geometry compute or local model inference is implemented. Every history snapshot is checked against bounded content/executable-keyed validated results or evaluated through Rust. New edits still launch Rust and rebuild the whole model; this is not the final large-document scheduler. See [runtime measurements](../../examples/ai-cad/runtime/README.md).

No general geometric sketch solver, arbitrary curved profiles, general booleans, blind/arbitrarily oriented holes, fillets, transforms, assemblies, collaborative editing protocol or production crash-recovery guarantee is added here. Bounded analytic through-holes and explicit STL/optional STEP export are available as described below. Atomic replace plus file/directory fsync is tested with injected failures; filesystem/power-loss behavior on physical hardware is not certified. Checksums detect accidental corruption, not hostile tampering.

The C++/OCCT foundation and earlier research remain separate and intact. Existing repository ownership/license status applies; see [dependency attribution](THIRD_PARTY.md). Report issues with the command JSON, error, platform, and Rust/Python versions; remove private design data before sharing.

## Round holes and usable exports

The [mounting bracket workflow](../../examples/ai-cad/bracket/README.md) creates and widens a flat plate with three analytic cylindrical holes. Thickness, radius and edge margins remain fixed; hole positions follow the existing affine rules. The exact model uses rational coordinates/radii and symbolic volume involving π. Only the disposable display/STL mesh uses chord approximations.

The browser downloads the saved revision as STL; the export CLI also supports optional STEP translation and independently checks readback. Export refuses stale revisions and existing output paths. STEP/STL omit feature history: retain the native document. See [validation and precision limits](../../docs/analytic-bracket-validation.md). Run `python3 tools/ai-cad/verify_bracket_example.py` in addition to the existing checks; the optional STEP verifier requires `step-requirements.txt`.

## Draw and edit a sketch

Start the viewer against a new document path, click **New sketch → solid**, place points around a simple outline (inward corners are allowed) (or start a rectangle), choose height, preview and save. **Edit sketch** supports point dragging and exact coordinate fields on existing profiles. Fixed/derived coordinates stay locked; shared parameter references move together. New drawings support 3..16 points, 1 mm drag snapping and integer/fraction field input. Preview runs the authoritative Rust checks before saving. [Browser recording, native documents and screenshots](../../examples/ai-cad/sketch-editor/README.md).

## Concave plates

[The L-shaped mounting plate](../../examples/ai-cad/concave-profile/README.md) adds a simple concave outline with two exact circular holes and a width-dependent mount. It includes native snapshots, STL, STEP, and independent re-import validation. Run `python3 tools/ai-cad/verify_concave_example.py`; optional OCCT validation is `python3 tools/ai-cad/verify_concave_export.py` after installing `step-requirements.txt`.

## Place and edit round holes

On a saved profile extrusion or cylinder, click **Add through-holes**, then place circle centers in the top-view outline. Drag circles or enter exact X/Y/radius values, preview, and save. New groups support up to 16 holes, subject to the document parameter limit. **Edit holes** changes dimensions and adds/removes holes while retaining surviving IDs. Emptying a group previews removal of its feature; unused parameters remain available for explicit reuse or cleanup. Shared references move together; fixed and derived fields stay locked. Circles must remain inside the profile and separate. The editor reports the engine's error and keeps the draft if validation or revision checking fails. [Actual browser recording, editable snapshots, screenshots and STL](../../examples/ai-cad/hole-editor/README.md).

Verify with `node --test tools/ai-cad/test_sketch.mjs tools/ai-cad/test_hole_editor.mjs` and `python3 tools/ai-cad/verify_hole_recording.py`. The latter replays exact document outputs and independently checks the recorded display mesh and saved STL geometrically, allowing platform-specific trigonometric rounding.

## Change feature structure

CLI/MCP support `replace_feature` (same ID/kind and timeline position), `remove_feature` (no implicit cascade), and `remove_parameter` (all references/constraints must be resolved). The browser hole dialog uses those operations to add/remove circles or remove an empty group. Complete-model validation, preview, revision checks, idempotent save and undo apply to structural edits. [Runnable browser recording and explicit cleanup example](../../examples/ai-cad/feature-edits/README.md). Run `python3 tools/ai-cad/verify_feature_edits.py`.

## Preserve horizontal and vertical edges

In **Edit sketch** or a new drawing, expand **Edge relationships**. Horizontal makes the end Y follow the start Y; vertical makes end X follow start X. These are directed exact affine links. Driven coordinates lock and rebuild on preview; edit their controlling coordinates. Existing different relationships must be cleared explicitly before replacement. **Clear X/Y link** retains the current value and restores direct editing unless it is also fixed. Cycles reject with a dependency path. This is not a simultaneous geometric constraint solver or a claim of fully constrained sketches. [Actual browser recording, native stages and cycle rejection](../../examples/ai-cad/sketch-relationships/README.md).

## Circular stock and flanges

`cylinder` creates exact circular stock; `through_holes` also accepts that stock. [The round flange example](../../examples/ai-cad/round-flange/README.md) grows radius40→50 while mounting holes retain a10 mm center-to-edge margin. Exact volume changes7410π→11910π mm³. CLI/MCP creates stock; the browser edits dimensions and places/edits holes on a circular top view. Native geometry stays analytic; STL/display declare chord error and can refuse clearances below their resolution. STEP keeps circular/cylindrical surfaces through an explicit boundary adapter. Run `verify_round_example.py` and optional `verify_round_export.py`.

The viewer [rebases display coordinates on the CPU](../../examples/ai-cad/gpu-precision/README.md) before float32 GPU upload. Camera motion retains buffers. Native coordinates and export tolerances remain unchanged; mixed-scale assemblies are not addressed by this compact-model fix.

[Blind-hole workflow](../../examples/ai-cad/blind-holes/README.md) supports flat-bottom cylindrical pockets with one exact depth per group. Browser creation/editing and MCP share depth, floor and containment checks. Run `python3 tools/ai-cad/verify_blind_example.py`; optional STEP validation uses `verify_blind_export.py`.

[Plane-cut workflow](../../examples/ai-cad/plane-cuts/README.md) integrates arbitrary exact half-spaces on convex planar solids, including sequential cuts and upstream edits. Run `python3 tools/ai-cad/verify_plane_example.py`; optional STEP checks use `verify_plane_export.py`.

Start a new browser document with `python3 tools/ai-cad/viewer.py --store work/new-part.cad.json`, then choose **New block or circular stock** or **New sketch → solid**. The [full browser example](../../examples/ai-cad/browser-stock/README.md) creates two parts, edits them and exports a single STL ZIP. Single-body downloads remain STL; multi-body ZIPs include a revision/units/precision manifest.

Use **Download editable project** to keep the native model and history. **Import saved model…** previews a file before **Replace model** saves one undoable replacement. To reopen the source history directly, use the downloaded file as `--store`. [Native workflow and verified downloads](../../examples/ai-cad/native-project/README.md).

[Browser sketch plane cuts](../../examples/ai-cad/sketch-plane/README.md) now accept convex `planar_profile` extrusions. Changing an upstream sketch rebuilds its cuts; simple concave edits are now supported. The retained historical recording includes the former rejection. Run `verify_sketch_plane.py` and optional `verify_sketch_plane_export.py`.

[Convex solid intersection](../../examples/ai-cad/intersection/README.md) keeps common volume through typed MCP commands or **Intersect two solids** in the browser. Inputs remain editable; empty results reject atomically. Run `verify_intersection.py` and optional `verify_intersection_export.py`.

Click a solid or use its feature-list **Select solid** button to highlight it and inspect its stable ID/exact volume. [Viewport selection and measured CPU/GPU behavior](../../examples/ai-cad/body-selection/README.md). Selection/orbit retain GPU buffers and do not save the model.

Use **Move solid** / **Edit move** for exact XYZ translation of convex planar bodies, including movement before an intersection. [Editable positioned parts and export checks](../../examples/ai-cad/translation/README.md). Run `verify_translation.py` and optional `verify_translation_export.py`. Planar Boolean results, including cavities and separate pieces, are also supported; analytic curved stock also supports these rigid placements.

Use **Quarter-turn solid** / **Edit turn** to orient convex planar parts by exact 90°, 180° or 270° rotations about a global axis through a parameter-backed pivot. [Editable rotation and export evidence](../../examples/ai-cad/quarter-turn/README.md). Run `verify_rotation.py` and optional `verify_rotation_export.py`. Planar Boolean results, including cavities and separate pieces, are also supported; arbitrary angles remain open; circular stock and hole groups now support quarter turns.

Selecting a saved body now shares its ID and current geometry with `cad_context` in the connected MCP client. Any model edit invalidates that selection until you reselect; preview selections remain local. Restart an existing MCP client to discover the additional read-only tool. [Browser-to-MCP selection evidence and workspace semantics](../../examples/ai-cad/shared-selection/README.md). Run `verify_selection_recording.py`.

Use **Explain solid** after selecting a saved body, or call `cad_explain(expected_revision, feature_id)`, to inspect controlling features, fixed/derived dimensions and potential impact across parts. [Model intent evidence](../../examples/ai-cad/model-intent/README.md). Explanations are read-only; dependency reachability does not replace preview validation. Run `verify_intent_recording.py`.

Browser previews now use a bounded background CPU queue with **Cancel calculation**. Cancelling preserves your draft and saved model; Save edit still commits explicitly at the preview revision. [Queue limits, cancellation tests and measured evidence](../../examples/ai-cad/preview-jobs/README.md). Run `verify_preview_recording.py` and `node --test tools/ai-cad/test_preview_client.mjs`. CLI/MCP and native-import previews remain synchronous.

## Planar union, difference and intersection

**Combine solids** consumes two terminal convex planar bodies or previous Boolean results. Choose union, difference (first minus second), or intersection. Results can have concave faces, holes, enclosed cavities and separate solid pieces. **Edit Boolean** changes the operation while retaining its inputs; upstream dimensions remain editable. Empty/nonmanifold results reject without saving. Simple concave profile extrusions are also supported; general curved inputs remain unsupported.

The original Rust implementation retains disjoint convex cells and merges exposed planar patches into a boundary. Float tessellation handles concave faces and face holes; STEP translates the supplied component/shell topology. No OCCT operation computes native model geometry. See the [recorded browser/MCP workflow and independent STEP comparisons](../../examples/ai-cad/planar-booleans/README.md) and [bounded contract](../../docs/ai-cad-contract.md#planar-solid-booleans).

## Move and orient Boolean results

**Move solid** and **Quarter-turn solid** now handle complete planar Boolean results, including through-holes, cavities and separate pieces. Their exact backing cells remain available for subsequent Booleans. Whole-result placement remains parameter-backed and undoable; individual component instances and arbitrary-angle rotations are not yet supported. See [native files, actual browser/MCP recordings and STEP/STL verification](../../examples/ai-cad/planar-transforms/README.md).

## Trim nonconvex planar results

**Cut with plane** and **Edit plane** now accept planar Boolean results and their rigid transforms. A cut can open a cavity into a pocket, trim a hole, or remove separated pieces; it retains exact cells for later transforms/Booleans. Empty results reject atomically. [Browser/MCP recordings, native history, pocket STL and independent STEP references](../../examples/ai-cad/nonconvex-plane-cuts/README.md) are included. Analytic curved stock remains unsupported.

## Operations on simple concave stock

Unperforated simple XY profile extrusions now feed Boolean operations, movement, quarter turns and plane cuts. Exact rational ear clipping builds disjoint triangular prisms without changing source history or using display triangles. [Native/browser/MCP and independent STEP evidence](../../examples/ai-cad/concave-operations/README.md) includes both windings, tiny rational coordinates and a split U-profile. Run `verify_concave_operations.py`; optional transport/export checks use `verify_concave_operations_mcp.py` and `verify_concave_operations_export.py`. Legacy `intersection` remains convex-only.

## Linked part placement

Use **Linked copy** on a planar solid and **Edit linked copy** on its placement. The source remains available and its dimensions drive all linked copies; placement offsets are independent. A copy can feed existing cuts, turns and Booleans. [Native history, browser/MCP recordings, parts ZIP and independent STEP comparisons](../../examples/ai-cad/linked-instances/README.md) demonstrate shared source editing and independent placement. Run `verify_instances.py`; optional MCP/STEP checks use `verify_instances_mcp.py` and `verify_instances_export.py`. This is in-document linked placement; assembly joints, external part libraries and GPU instancing remain open.

## Exact planar measurements

Select a saved planar part and choose **Measure solid**, or call MCP `cad_measure` with its saved revision and feature ID. Exact world bounds, volume centroid and centroidal volume inertia are shared by both interfaces. [Measurements, retained native input, actual browser/MCP requests and independent references](../../examples/ai-cad/measurements/README.md) explain units and supported geometry. No material density or physical mass is assigned. Run `verify_measurements.py`, optional `verify_measurements_mcp.py` and optional OCCT `verify_measurements_reference.py`.

## Place circular and perforated parts

**Move solid**, **Quarter-turn solid** and **Linked copy** now accept circular stock and parts with through/blind holes. Exact local circles/cylinders and depth parameters remain intact; composed placement carries them into world coordinates for display and STEP/STL. [Native history, actual browser/MCP and independent analytic STEP evidence](../../examples/ai-cad/analytic-placement/README.md) includes a turned flange with editable blind pockets. Run `verify_analytic_placement.py`, optional `verify_analytic_placement_mcp.py` and optional `verify_analytic_placement_export.py`. Curved Boolean/cut operations remain unsupported.

## Measure round and perforated parts

Measure solid and `cad_measure` also support circular stock, through/blind holes and their placements. Centroids and volume inertia remain exact expressions involving π; bounds remain rational. [Editable source/copy depth workflow and fifteen independent references](../../examples/ai-cad/analytic-measurements/README.md) document the format and units. Run `verify_analytic_measurements.py`; optional MCP and reference checks use `verify_analytic_measurements_mcp.py` and `verify_analytic_measurements_reference.py`. No density or physical mass is assigned.

[Request-local CPU reuse](../../examples/ai-cad/transaction-reuse/README.md) avoids duplicate rebuilding of a validated unchanged feature prefix. Six baseline-equivalent workloads include 32-feature linked models; measured inspection/late-edit gains are about 1.8–1.9× on the recorded host, while root edits remain unchanged. Run `python3 tools/ai-cad/verify_rebuild.py` for exact retained replies, and Rust tests with `--release` for the full differential corpus. This does not add a persistent worker or cross-request geometry cache.

[Exact counterbores](../../examples/ai-cad/counterbores/README.md) combine a through aperture with a wider flat-bottom recess, preserving analytic cylindrical walls, annular shoulders and exact symbolic measurements. Browser/MCP creation, native history, downloaded STL and eight independent STEP comparisons are retained. One group shares recess radius/depth; individual through radii remain editable.

### Inspect shared surfaces

Select a saved solid and choose **Inspect surfaces**, or call `cad_topology(expected_revision, feature_id)` through MCP. Exact planes/cylinders, shared edges and closed shells expose the boundary behind the display mesh. Analytic surface names follow authored feature/hole/profile IDs, scoped to a body and revision; planar evaluated face indices remain revision-only. Refresh after edits. See the [contract](../../docs/ai-cad-contract.md#shared-surface-topology) and [recorded examples](../../examples/ai-cad/shared-topology/README.md).

```sh
python tools/ai-cad/verify_topology_mcp.py
python tools/ai-cad/verify_topology_recording.py
# Optional STEP comparison environment:
python tools/ai-cad/verify_topology_export.py
```

Inside **Inspect surfaces**, expand a surface and choose **Select surface** to share it with AI tools. `cad_context` then returns its exact support, owning feature and body/revision scope; `cad_select_surface` can explicitly select an inspected saved reference. Use `cad_explain` on the owner to see shared dimensions and affected copies. Any model edit requires reselection. [Recorded surface-context workflow](../../examples/ai-cad/surface-context/README.md).

```sh
python tools/ai-cad/verify_surface_context_mcp.py
python tools/ai-cad/verify_surface_context_recording.py
```

For an AI edit based on shared context, supply the same `selection_guard:{feature_id,surface_id}` to `cad_preview` and `cad_commit`. Use a null surface only for a body-only selection. A selection change at the same model revision now rejects the guarded save; inspect/replan instead of dropping the precondition. Browser edits automatically retain the currently selected surface. [Recorded guarded-save conflict and recovery](../../examples/ai-cad/selection-guard/README.md).

```sh
python tools/ai-cad/verify_selection_guard_mcp.py
python tools/ai-cad/verify_selection_guard_recording.py
```

You can also click a visible surface directly in the viewport. The chosen native cap, wall or shoulder is validated and shared with AI tools, then highlighted separately; choose **Select solid** in the feature list for whole-body context. Surface picking uses the displayed mesh and saved revision. [Recorded picks and zero-upload highlighting](../../examples/ai-cad/surface-picking/README.md).

```sh
python tools/ai-cad/verify_surface_picking.py
```

### Tapered round stock

Choose **New solid stock → Tapered round stock** to enter the center, bottom/top radii and height. Both radii must be positive and different. Preview/save, surface picking, exact measurement, movement, quarter turns, linked copies and STEP/STL exports work with the analytic conical wall. Holes and curved Booleans remain unsupported. [Native files, recorded browser/MCP workflow and independent STEP evidence](../../examples/ai-cad/tapered-stock/README.md).

```sh
python tools/ai-cad/verify_frustum.py
python tools/ai-cad/verify_frustum_mcp.py
# Optional comparison environment:
python tools/ai-cad/verify_frustum_export.py
```

### Startup recovery

If the workspace cannot finish loading, use **Reload workspace** after checking that the local viewer is running. The viewer handles idle browser preconnections with bounded connection parsing while preserving serialized model requests. [Socket regression tests and an actual interrupted-load/recovery demonstration](../../examples/ai-cad/startup-recovery/README.md) document its limits.

### Countersunk holes

Choose **Countersunk through** in the hole editor for a conical recess over each aperture. Set the shared rim radius and depth; the angle follows those dimensions. Positive depth stays below stock height, and the larger rims stay inside stock and apart. Surface context, exact measurements, linked placement and exports remain available. [Native history, browser/MCP recordings and independent STEP evidence](../../examples/ai-cad/countersinks/README.md).

```sh
python tools/ai-cad/verify_countersinks.py
python tools/ai-cad/verify_countersinks_mcp.py
# Optional comparison environment:
python tools/ai-cad/verify_countersinks_export.py
```

### Individual blind-hole depths

Choose **Blind · flat bottom**, then set a per-hole depth or leave it blank to use the group depth. Existing individual depths can return to the shared value with **Use group depth**. Preview validates each remaining floor; fixed/derived depth values retain their constraints. [Examples and verification](../../examples/ai-cad/individual-depths/README.md).

```sh
python tools/ai-cad/verify_individual_depths.py
python tools/ai-cad/verify_individual_depths_mcp.py
# Optional comparison environment:
python tools/ai-cad/verify_individual_depths_export.py
```

### Standalone sketches and planar lofts

Choose **Save sketch only** in the sketch editor to retain a profile without an extrusion. **Loft profiles** joins matching convex sections at a specified height, with exact planar side faces. Preview rejects twisted/nonplanar sides. Source sketch and height edits rebuild the solid; planar cuts, Booleans, placement and exports remain available. [Editable examples, browser/MCP recordings and limits](../../examples/ai-cad/planar-loft/README.md).

```sh
python tools/ai-cad/verify_planar_loft.py
python tools/ai-cad/verify_planar_loft_mcp.py
# Optional comparison environment:
python tools/ai-cad/verify_planar_loft_export.py
```

### Native worker runtime

The host reuses one serial Rust worker for native operations, reducing process-start overhead while preserving request-local validation and atomic saving. Requests/replies and lock/pipe deadlines are bounded; failed calls are not automatically retried. Rebuild the current engine after updating host code. The single-request CLI remains available. [Measurements, failure tests and runtime evidence](../../examples/ai-cad/native-worker/README.md).

```sh
python tools/ai-cad/verify_native_worker.py
python tools/ai-cad/benchmark_native_worker.py --samples 15
```

### Exact edge measurements

Select a saved solid, choose **Inspect surfaces**, select an edge and choose **Measure edge**. The inspector reports exact length, display approximation, endpoints and chord separately, and labels smooth surface seams. Numbers apply only to that saved revision; refresh after edits. AI clients use `cad_topology` followed by `cad_measure_edge` with the returned body/revision and zero-based index. [Editable examples and evidence](../../examples/ai-cad/edge-measurements/README.md).

```sh
python tools/ai-cad/verify_edge_measurements.py
python tools/ai-cad/verify_edge_measurements_mcp.py
# Optional comparison environment:
python tools/ai-cad/verify_edge_measurements_reference.py
```

A successful edge measurement now [highlights its viewport location](../../examples/ai-cad/edge-highlight/README.md) in purple with endpoint markers. Orbit to see occluded portions. Changing the edge/selection or starting an edit clears the old highlight; display sampling does not change exact length.

### Planar part overlap

Select a saved planar solid, choose another body in **Compare with another planar solid**, then **Check volume overlap**. The exact common volume respects cavities and disconnected material. A zero result may still mean the parts touch; this does not measure clearance. AI clients use `cad_interference` at the current revision. Curved stock is explicitly unsupported. [Examples and independent comparisons](../../examples/ai-cad/interference/README.md).

```sh
python tools/ai-cad/verify_interference.py
python tools/ai-cad/verify_interference_mcp.py
# Optional comparison environment:
python tools/ai-cad/verify_interference_reference.py
```
