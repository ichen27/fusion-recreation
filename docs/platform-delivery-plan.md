# AI-native CAD platform delivery plan

Scope confirmed 2026-10-19: pursue the full long-term platform. A bracket workflow and a first usable release are acceptance milestones within this scope. This plan records scope, dependencies, evidence and unresolved decisions; it is not a promise of a completion date or a claim of feature parity.

## Established direction

- Original geometry/modeling engine, with current custom development in Rust. No silent OCCT modeling fallback. Earlier C++/OCCT work stays available as a separate reference/integration track.
- AI and human actions share typed modeling operations, one authoritative editable document, exact diagnostics, previews and reversible commits.
- Single-user browser workflow first; computation/storage on the Mac mini SSD. Client GPU rendering and exact CPU geometry remain distinct. Measure before choosing GPU compute workloads.
- Deliver coherent feature branches through tests, reviewed PRs and verified CI. Retain runnable examples, native editable documents and usable exports. Keep repositories private until release visibility and licensing are explicitly settled.

## Capability ledger and acceptance gates

| Gate | Status | Acceptance evidence | Major unresolved work |
|---|---|---|---|
| Original planar geometry | Bounded implementation | Exact convex clipping, convex/simple-concave profile extrusion, orientation/manifold tests and independent comparisons | General nonconvex Boolean operations, multiple shells/cavities and tolerance policy beyond rational planes |
| Editable model and AI loop | Bounded implementation | Recorded create/edit conversation; typed MCP; atomic save/reopen, preview and undo | Broader intent tests, semantic selections, ambiguity handling and repair benchmarks |
| Parameter relationships | Bounded implementation | Center follows width; dependent chains rebuild exactly; cycles/conflicts reject atomically; same results through CLI/MCP/browser | General geometric constraint solving and nonlinear expressions |
| Useful part workflow | Bounded flat-bracket implementation | Three analytic through-holes; margin/center relationships; preview/save/reopen/undo; STL topology and STEP surface/location/volume checks | Bent brackets, arbitrary hole axes/depths, general curved topology and wider intent corpus |
| Sketch and feature modeling | Interactive polygon editing implemented | Interactive constrained sketches and edit-stable extrude/revolve/sweep/loft/hole/chamfer/fillet/shell/draft/pattern workflows | Solver choice, over/underconstraint diagnostics, selection provenance and robust curved intersections |
| Geometry breadth and interchange | Planned | Analytic and spline surfaces, repeated nonconvex operations, valid native/STEP/STL round trips with explicit losses | Curved numerical policy, trimming/healing, NURBS and imported-boundary validation |
| Runtime and hardware | Bounded host/mesh caching and retained GPU buffers implemented | Versioned jobs, cancellation, incremental rebuilds, memory budgets and latency/frame-time measurements on declared workloads/devices | Large-document scheduling, caches, worker concurrency, GPU uploads/device recovery and justified compute acceleration |
| Assemblies and engineering documentation | Planned | Component transforms, joints/configurations, linked drawings, tolerances and parts lists survive model edits | Assembly references, configuration semantics, materials, sheet metal and associative drawings |
| Broader design workflows | Planned | Explicitly scoped surfaces/freeform, meshes, rendering and animation examples | Representations, conversion semantics and cross-workflow editability |
| Manufacturing and analysis | Long-term scope | Separate verified CAM, additive/nesting, CAE and electronics workflows | Domain solvers, toolpaths/posts, machine/process models, numerical accuracy and independent validation |
| Product delivery and collaboration | Planned | Reproducible installation/update, stable document migrations, recoverability, API/add-ins, versioning and collaboration tests | Packaging/deployment, licensing/business model, access controls and concurrent editing semantics |

“Implemented” applies only to the tested capabilities stated in each row. Earlier standalone experiments are references until integrated and revalidated. A screenshot or one accepted AI prompt is not an acceptance gate by itself.

## Immediate implementation sequence

1. Exact affine parameter relationships, shared validation and dependency diagnostics. Preserve existing document/replay behavior.
2. Define analytic round-hole geometry and its precision policy; integrate a bounded round-hole part path without substituting polygons as authoritative circles.
3. Add usable export with measured approximation where applicable and independent re-import checks. Supporting export adapters must be explicit about geometry/history losses.
4. Complete the bracket create/edit/save/reopen/export acceptance run through the shared AI and human workflow. Specify the bracket geometry and required edits in its fixture, not just its visual appearance.
5. Measure cold/warm operation cost, peak memory and browser frame/upload behavior on a representative corpus. Use results to guide incremental evaluation and scheduling.
6. Expand sketches, general solids and curved operations, each with accepted/rejected case corpora and edit-stability tests.

These steps may overlap when dependencies allow. A failed geometry or performance gate triggers a documented diagnosis and revised implementation, not a substituted success claim.

## Decision handling

Routine internal implementation choices can proceed within this scope. Record choices and tradeoffs alongside relevant code. Product-changing decisions still need concrete alternatives: supported manufacturing domains, public release/license, paid infrastructure, distribution beyond the existing host, and incompatible data/precision policies. Do not repeatedly reopen established browser/mini/custom-engine preferences.

Progress reporting identifies the completed gate, evidence, remaining limits, source revision and next dependency. The full platform remains in progress until its agreed acceptance gates are met; completing an individual PR does not complete this plan.

## Latest evidence

[Parameter relationship validation](parameter-relationship-validation.md) records the current dependency behavior, integration checks and measured full-history latency. Broader runtime and GPU measurements remain pending.

[Analytic bracket validation](analytic-bracket-validation.md) records the integrated hole, display and export milestone. Next: measured runtime/frame/upload behavior, then broader sketch interaction and geometry. The full platform remains in progress.

## Runtime checkpoint

[Measured bounded reuse and rendering](../examples/ai-cad/runtime/README.md) removes repeated host validation/tessellation and camera-time mesh uploads without changing exact geometry. Content/executable invalidation, memory limits and context recovery are covered. Feature-level incremental evaluation, asynchronous cancellation and large-model scheduling remain pending. Continue directly into interactive sketch creation after this checkpoint; a merged PR is not a stop condition.

## Interactive sketch checkpoint

[Browser sketch creation/editing](../examples/ai-cad/sketch-editor/README.md) adds point placement, dragging and exact coordinate inputs through the same typed preview/save contract. A four-call actual browser recording replays native documents. This is convex polygon editing with existing affine/fixed constraints, not a general geometric sketch solver. Continue with nonconvex planar profiles and broader solids.

## Concave profile checkpoint

[Simple concave extrusion and holes](../examples/ai-cad/concave-profile/README.md) extends the custom engine to L-shaped plates with exact segment-distance clearance checks. Old convex feature behavior is preserved. STEP re-import is compared to an independent union/cut oracle used only in verification. Next: interactive hole authoring, followed by broader intent and geometry workflows.

## Interactive hole checkpoint

[Through-hole placement/editing](../examples/ai-cad/hole-editor/README.md) completes a browser sketch→extrusion→hole group→dimension edit→save/reopen→STL workflow through the same commands as MCP. The editor preserves semantic references and constraints; rejected/stale previews retain the draft. Next modeling work expands feature editing and sketch relationships without claiming a general constraint solver.

## Structural edit checkpoint

[Feature replacement/removal and explicit cleanup](../examples/ai-cad/feature-edits/README.md) keeps original feature IDs/kinds and validates dependencies across complete atomic edits. The browser can add/remove circles in an existing group and remove an empty group; unused parameters remain until explicitly removed. General feature reordering, generated topology naming and broader curved operations remain open.

## Directed sketch relationship checkpoint

[Horizontal/vertical edge links](../examples/ai-cad/sketch-relationships/README.md) exposes exact affine dependencies in the browser sketch editor. A rectangle resizes while retaining edge orientation, an explicit unlink restores direct editing, and a cyclic relationship rejects without saving. Degrees-of-freedom analysis, redundant-constraint handling, arbitrary-angle constraints and a simultaneous solver remain open.

## Round-stock checkpoint

[Exact circular stock and flanges](../examples/ai-cad/round-flange/README.md) adds cylindrical outer boundaries, exact circular hole containment, parameter-linked mounting positions, browser editing and independently checked STEP/STL. Native geometry is analytic; display/export resolution limits are explicit. General curved B-rep intersections, arbitrary-axis operations and revolve/sweep/fillet remain open. Next runtime work rebases GPU display coordinates to preserve small geometry far from the origin.

## GPU precision checkpoint

[CPU rebasing before GPU upload](../examples/ai-cad/gpu-precision/README.md) preserves compact geometry far from the origin while retaining camera-only buffer reuse. Actual before/after browser evidence and context recovery are recorded. Native coordinates remain unchanged. Mixed-scale assemblies and float64 tessellation precision still require separate policies.

## Blind-hole checkpoint

[Depth-controlled blind holes](../examples/ai-cad/blind-holes/README.md) add flat floors with exact depth/remaining-material checks, browser editing and independent STEP solid classification below/above each floor. The same stock can be polygonal or circular. Mixed depths, arbitrary axes and general curved intersections remain open.

## Three-dimensional plane-cut checkpoint

[Sequential arbitrary-plane cuts](../examples/ai-cad/plane-cuts/README.md) integrates the original exact convex boundary clipper into typed model features and browser controls. Upstream plane edits rebuild later cuts; empty solids reject atomically. Independent STEP half-space comparisons and native recordings are included. General nonconvex/curved Booleans and persistent generated topology references remain open.

## Viewport framing checkpoint

[Orientation and aspect-aware fit](../examples/ai-cad/viewport-framing/README.md) keeps bounded geometry visible at default zoom across window shapes, adds Fit view and retains GPU buffers on camera/resize operations. View presets, panning and semantic selection remain open.

## Browser stock and multi-body delivery checkpoint

[Creation from an empty document](../examples/ai-cad/browser-stock/README.md) now supports block/circular stock and existing cut/hole editors without CLI model setup. Eleven actual browser calls and a downloaded two-body ZIP verify native editing, atomic rejection, undo/redo and consistent-revision export. Document management, assembly structure and broader geometry remain open.

## Native project checkpoint

[Native download and import](../examples/ai-cad/native-project/README.md) retain editable history in downloads and make importing a model an explicit undoable replacement. Actual browser records, downloaded files and corruption/stale/retry tests verify the workflow. Project libraries, document migrations and multi-user synchronization remain open. Next: connect browser-created convex sketches to existing three-dimensional plane cuts without approximating concave or curved solids.

## Convex sketch/cut integration checkpoint

[Browser sketches feed exact plane cuts](../examples/ai-cad/sketch-plane/README.md) through an exact convexity-checked boundary construction. Existing simple-profile output remains stable, and invalid downstream edits are atomic. Eight actual browser calls, native history and independent STEP/STL checks verify the path. Continue into bounded solid/solid Boolean operations before extending to general nonconvex and curved intersections.

## Convex solid intersection checkpoint

[Exact solid intersection](../examples/ai-cad/intersection/README.md) keeps the common volume of two convex planar bodies, including browser sketches and previous cuts/intersections. Both inputs remain in editable history. Typed MCP, ten actual browser calls, rational/seeded/contact cases and independent STEP Booleans verify the bounded operation. Union/difference, disconnected/nonconvex results, curved topology and broader semantic selections remain open.

## Viewport body selection checkpoint

[Body selection and highlighting](../examples/ai-cad/body-selection/README.md) identifies stable terminal feature IDs from displayed triangles, supports feature-list keyboard selection and preserves retained GPU buffers. Actual context-loss recovery and CPU picking measurements are recorded. Exact face/edge picking, snapping and persistent generated-topology naming remain open.

## Exact planar movement checkpoint

[XYZ movement](../examples/ai-cad/translation/README.md) positions convex planar parts through parameter-backed offsets and rebuilds downstream cuts/intersections. Twelve actual browser calls, typed MCP, rational boundary tests and independent positioned-box export checks verify the workflow. Arbitrary rotation, curved/nonconvex movement, component instances and assembly joints remain open.

## Exact orientation checkpoint

[Quarter-turn rotation](../examples/ai-cad/quarter-turn/README.md) orients convex planar parts about exact pivots without changing dimensions or volume. Twelve actual browser calls, all axes/angles with fractional pivots, inverse rotations, downstream rebuild/rejection, typed MCP and independent STEP/STL checks cover the bounded workflow. Arbitrary-angle precision, curved/nonconvex transforms and assembly instances remain open. Next: share explicit body-selection context between human interaction and AI tools, with revision checks so stale picks cannot silently refer to changed geometry.

## Shared selection checkpoint

[Browser-to-MCP context](../examples/ai-cad/shared-selection/README.md) binds a selected terminal body to saved content and revision. Actual browser selection and MCP edits demonstrate invalidation, reselect and clear; native history remains unchanged. This closes the ambiguity between a visible pick and an AI reference for one body. Persistent face/edge naming, selection-specific commit guards, intent ambiguity benchmarks and multi-user context remain open.

## Model-intent checkpoint

[Original-engine provenance and impact](../examples/ai-cad/model-intent/README.md) explains controlling features, root drivers, fixed/derived values and potentially affected bodies. Actual browser/MCP explanations are checked against a shared-driver edit on two parts. The engine uses exhaustive typed references and validates source models; it does not infer semantic intent or replace preview validation. General sketch constraints, persistent face references and broader intent benchmarks remain open.
