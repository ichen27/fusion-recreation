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
| Original planar geometry | Bounded implementation | Exact profile decomposition, nonconvex planar Booleans/cuts, cavities/components and independent shape comparisons | Curved Boolean operations, imported-boundary validation and tolerance policy beyond rational planes |
| Editable model and AI loop | Bounded implementation | Recorded create/edit conversation; typed MCP; atomic save/reopen, preview and undo | Broader intent tests, semantic selections, ambiguity handling and repair benchmarks |
| Parameter relationships | Bounded implementation | Center follows width; dependent chains rebuild exactly; cycles/conflicts reject atomically; same results through CLI/MCP/browser | General geometric constraint solving and nonlinear expressions |
| Useful part workflow | Bounded flat-bracket implementation | Three analytic through-holes; margin/center relationships; preview/save/reopen/undo; STL topology and STEP surface/location/volume checks | Bent brackets, arbitrary hole axes/depths, general curved topology and wider intent corpus |
| Sketch and feature modeling | Interactive polygon editing implemented | Interactive constrained sketches and edit-stable extrude/revolve/sweep/loft/hole/chamfer/fillet/shell/draft/pattern workflows | Solver choice, over/underconstraint diagnostics, selection provenance and robust curved intersections |
| Geometry breadth and interchange | Planned | Analytic and spline surfaces, repeated nonconvex operations, valid native/STEP/STL round trips with explicit losses | Curved numerical policy, trimming/healing, NURBS and imported-boundary validation |
| Runtime and hardware | Bounded host/mesh caching and retained GPU buffers implemented | Versioned jobs, cancellation, incremental rebuilds, memory budgets and latency/frame-time measurements on declared workloads/devices | Large-document scheduling, caches, worker concurrency, GPU uploads/device recovery and justified compute acceleration |
| Assemblies and engineering documentation | Linked planar placement implemented | Linked source dimensions and independent placement survive edits, native reopen and world-coordinate export | Assembly joints/configurations, external part references, materials, parts lists, sheet metal and associative drawings |
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

## Cancellable preview checkpoint

[Bounded CPU preview jobs](../examples/ai-cad/preview-jobs/README.md) move ordinary browser preview evaluation/display work into a cancellable process group. Snapshot jobs release the document lock, preserve revision preconditions and never save. Actual browser cancellation preserves drafts and native bytes with zero GPU uploads; process tests cover child termination, independent worker deadlines and queue/memory limits. Per-viewer limits do not provide machine-wide scheduling; persistent workers, incremental rebuilds and representative large-model measurements remain open.

## Planar Boolean checkpoint

[Original planar union/difference/intersection](../examples/ai-cad/planar-booleans/README.md) now returns merged concave/holed faces, cavities and multiple components from bounded convex-cell operations. Browser/MCP creation and operation editing preserve history; STEP/STL retain component/shell topology. Nine independent OCCT comparisons check directed residual volumes and surface area as well as volume, and recorded browser rejection/undo stages replay. Curved intersections, general imported B-reps, persistent topology naming and scalable incremental evaluation remain open. Continue with transforms of these new planar results and stronger reusable component semantics.

## Nonconvex rigid-operation checkpoint

[Moved/turned planar results](../examples/ai-cad/planar-transforms/README.md) preserve cavity shells, face holes and disconnected pieces through exact whole-result placement. Backing cells survive for later Booleans. All quarter-turn axes/angles and fractional pivots, browser/MCP upstream edits and independent transformed STEP references are verified. Arbitrary angles, curved stock, per-component instances and assembly relationships remain open.

## Nonconvex plane-cut checkpoint

[Half-space cuts on planar results](../examples/ai-cad/nonconvex-plane-cuts/README.md) now open cavities, trim through-holes and remove components while retaining exact geometry for later operations. Browser/MCP edits, empty rejection, native undo and eight independent STEP comparisons cover the integrated workflow. Initial concave extrusions are still not admitted as inputs to the cell pipeline; next connect validated simple profiles through exact convex decomposition without a floating-point modeling fallback.

## Concave-stock checkpoint

[Exact simple-profile decomposition](../examples/ai-cad/concave-operations/README.md) now admits initial concave extrusions to Boolean, move/turn and cut operations. Both windings, 32-vertex profiles, tiny rational inputs and topology splitting are verified, alongside actual browser/MCP edits and seven independent STEP references. The next foundational gap is reusable part instances: current consuming transforms duplicate feature work and cannot express an assembly. Add explicit non-consuming linked instances before joints, with provenance, rebuild, selection and export semantics.

## Linked-instance checkpoint

[Non-consuming planar part instances](../examples/ai-cad/linked-instances/README.md) reuse source dimensions, retain independent placement and participate in subsequent operations and provenance. Browser/MCP, native history, separate STL ZIP and five independent STEP references are verified. Geometry is currently rebuilt per instance; no GPU instancing speedup is claimed. Next add exact engineering measurements of supported planar solids so humans and AI can inspect geometry beyond volume before broadening assembly constraints.

## Planar measurement checkpoint

[Exact bounds, centroids and volume inertia](../examples/ai-cad/measurements/README.md) are available read-only in browser/MCP for terminal planar solids. Closed-form and independent per-solid references cover concavity, cavities, separated material and transform covariance. Native history is unchanged; density/material assignment, curved analytic measurements, surface area and inter-part clearance remain open.

## Analytic placement checkpoint

[Exact placements for round stock and hole groups](../examples/ai-cad/analytic-placement/README.md) preserve analytic circles/cylinders through movement, quarter turns and linked reuse. Browser/MCP depth edits, rejection/undo, world-space blind floors and six independent STEP comparisons are verified. Curved Booleans, arbitrary rotations and curved-part measurements remain open.

## Analytic measurement checkpoint

[Symbolic-pi centroids and volume inertia](../examples/ai-cad/analytic-measurements/README.md) now cover circular/perforated stock and exact placements. Native coefficient checks, closed forms, symbolic identities, all-axis covariance, six browser/six MCP calls and fifteen independent analytic references are verified. Material density, surface area, principal axes, collision/clearance and new curved geometry remain open.

## Transaction CPU reuse checkpoint

[Validated feature-prefix reuse](../examples/ai-cad/transaction-reuse/README.md) removes a duplicate geometry pass on inspection and rebuilds only the suffix for late edits. All 63 model fixtures compare against full rebuilding, including valid/rejected edits and consumption/constraint semantics. Six paired workloads retain full replies and CPU samples; observed inspection/late-edit speedups are about 1.8–1.9×, with no meaningful root-edit gain. This is one-request reuse; cross-request dependency caching, persistent workers and larger-model scheduling remain open.

## Counterbore checkpoint

[Analytic stepped through-holes](../examples/ai-cad/counterbores/README.md) now expose shared upper recess radius/depth in browser/MCP while retaining per-hole through radii. Exact geometry, symbolic measurements, linked placement, twelve browser/eight MCP calls, native history and downloaded STL are verified. Eight independent STEP comparisons include concave stock, unequal through radii, circular stock and placements. Countersinks, threads, arbitrary axes, multiple groups and general curved Booleans remain open.

## Shared surface checkpoint

[Explicit shared native topology](../examples/ai-cad/shared-topology/README.md) now exposes exact planes/cylinders, oriented line/quarter-circle loops, closed shells and source-derived analytic surface names through browser/MCP. Exact support/incidence/orientation checks and independent STEP reconstruction cover holes, cavities and disconnected material. Names are scoped to a body and revision; general Boolean naming and imported B-rep validation remain open. Next connect surface context to precise human/AI inspection and targeted feature reasoning, retaining explicit revision guards before editing.

## Surface context checkpoint

[Shared surface selection](../examples/ai-cad/surface-context/README.md) connects browser inspection to MCP with exact world support, source feature, body and revision. Linked-copy context exposes shared-driver impact through the existing explanation tool. Actual browser-to-MCP handoff, parameter edits, stale/missing rejection and old body-only compatibility are verified. The viewport still highlights whole bodies; geometric surface picking and selection-bound edit preconditions remain ahead.

## Selection-bound edit checkpoint

[Optional preview/save selection guards](../examples/ai-cad/selection-guard/README.md) prevent a context-dependent edit from silently proceeding after the selected body/surface changes, even without a model revision change. Browser proposals retain surface guards; MCP accepts the same typed precondition. Tests cover snapshot jobs, explicit reselection, same-revision replacement, atomic rejection and idempotent receipts. This proves context identity, not edit locality or user authorization. Geometry picking, broader modeling operations and full engineering workflows remain open.

## Direct surface picking checkpoint

[Native triangle provenance and viewport picking](../examples/ai-cad/surface-picking/README.md) connect a visible cap/wall/shoulder directly to exact shared surface context. The original mesh builder retains source references, and CPU picking uses the same rebased display coordinates as the GPU. Only the chosen surface is highlighted; actual picking/orbit records show zero geometry uploads. Native geometry and untagged STL meshes remain unchanged. Exact curved ray intersections, edge picking, broader feature geometry and scalable rendering remain open.

## Tapered stock checkpoint

[Conical frustum stock](../examples/ai-cad/tapered-stock/README.md) adds exact conical walls, two circular caps, polynomial volume moments, placement/instances and surface provenance to the original engine. Twelve browser/ten MCP calls exercise creation, surface selection, guarded widening, rejection and undo; fourteen STEP readbacks compare with seven independent solid references. Apex cones, tapered holes/countersinks, general curved Booleans and arbitrary rotations remain open. Startup robustness and user-facing recoverability also need attention alongside added geometry.

## Startup recovery checkpoint

[Bounded connection handling and visible recovery](../examples/ai-cad/startup-recovery/README.md) prevent browser preconnections from monopolizing HTTP parsing. Model/cache operations remain serialized. Socket tests cover partial headers, budget exhaustion and conflicting writes; actual browser fault injection/reload and eight later loads preserve native bytes. Large-model scheduling and broader product packaging remain separate work.

## Countersink checkpoint

[Original conical through-hole recesses](../examples/ai-cad/countersinks/README.md) reuse exact conical supports with inward orientation, cylindrical apertures and symbolic moments. Browser/MCP authoring, guarded edits, native history and downloaded STL are retained; eight independent solid comparisons check STEP and shared topology. Mixed-depth groups, arbitrary axes, angle-driven authoring and general curved Booleans remain open.

## Individual blind-depth checkpoint

[Per-hole depth references](../examples/ai-cad/individual-depths/README.md) retain a shared default while allowing distinct flat floors within one group. Exact measurements, topology, placements and STEP use each resolved depth; browser fields can reconnect the default without deleting old parameters. Actual browser/MCP creation, edit, rejection and native history are retained. Counterbore/countersink groups still share recess dimensions. Broader profile construction and curved modeling remain open.

## Convex planar loft checkpoint

[Standalone sketches and exact planar lofts](../examples/ai-cad/planar-loft/README.md) support matching convex polygon sections, taper/skew and downstream planar operations. Exact side-planarity and convexity checks reject unsupported curved/twisted geometry. Fifteen browser calls create both profiles from empty, loft, resize, export, reject and undo; ten MCP calls and eight independent ruled-loft comparisons cover shared surfaces and exact moments. General curved/multisection lofts, differing vertex counts and concave sections remain open.

## Native worker checkpoint

[A bounded persistent native process](../examples/ai-cad/native-worker/README.md) serves five operation modes with deadline/error/replacement/fork isolation and unchanged exact replies. Ten measured workloads compare fresh CLI and warm worker calls; browser native-history loading plus explanation/measurement/topology reuse one process without document changes. This reduces process startup overhead; cross-request geometry reuse, parallel scheduling and GPU compute remain separate work.

## Exact edge measurement checkpoint

[Revision-bound edge lengths](../examples/ai-cad/edge-measurements/README.md) expose exact line and quarter-circle lengths through the browser and typed MCP. Chord length is separate; smooth patch seams are identified. Independent source-dimension identities, 196 translated-support integrations, strict/stale reference tests and actual browser/MCP recordings preserve native history. Viewport edge highlighting/picking and general entity distances remain open.

## Measured-edge highlight checkpoint

[A separate GPU overlay](../examples/ai-cad/edge-highlight/README.md) locates a measured line/arc with endpoint markers and depth occlusion. Body geometry stays resident while edge buffers are bounded to the sampled curve. Browser evidence covers orbit without uploads, context recovery, stale replies and draft clearing; native history remains unchanged. Shared edge context and direct edge picking remain open.

## Planar interference checkpoint

[Exact positive-volume overlap checks](../examples/ai-cad/interference/README.md) inspect pairs of saved planar parts without consuming geometry. Backing cells preserve cavities, concavity and disconnected material; native CPU half-space checks avoid display approximations. Browser/MCP results distinguish positive common volume from unresolved contact and explicitly reject curved stock. General contact/clearance, curved intersections, all-pairs scheduling and assembly joints remain open.

## Exact planar separation checkpoint

[Material distance and contact classification](../examples/ai-cad/clearance/README.md) distinguish separated, touching and overlapping planar parts, including cavities and disconnected pieces. Exact squared distances and rational closest points are checked against independent solids; limits reject incomplete searches. Browser/MCP preserve native history. Curved clearance, penetration depth, motion envelopes and tolerance-aware assembly analysis remain open. Next broaden original modeling with hollow planar parts for enclosures.

## Exact planar shell checkpoint

[Parameter-backed hollow parts](../examples/ai-cad/planar-shell/README.md) support convex planar stock, one optional opening and exact uniform inward wall thickness. Browser and typed MCP author/edit the same native feature; invalid thickness preserves saved history. Independent explicit inner solids verify twelve box/tapered/triangular/placed cases, STEP boundaries and moments. Irrational retained-plane offsets, curved/nonconvex shells, multiple openings and variable thickness remain open. Next broaden repeated modeling intent with linked parametric patterns while preserving exact source dependencies and bounded work.

## Linear material pattern checkpoint

[Exact repeated planar material](../examples/ai-cad/linear-pattern/README.md) keeps source dimensions and parameter-backed step dependencies inside one count-editable feature. Each copy is computed from the source at an integer multiple of the step; exact unions handle separated, touching and overlapping material. This deliberately differs from independent assembly instances. General curved/circular patterns, body-versus-feature identity for multi-output assembly features and larger-model scheduling remain open.

## Exact planar mirror checkpoint

[Reflection across rational planes](../examples/ai-cad/mirror/README.md) supports oblique symmetry, optional linked source retention and exact dependent edits. Native boundary orientation, double-reflection recovery, browser/MCP history and nine independent STEP/moment comparisons are verified. Curved reflections, arbitrary-angle rotations and persistent face naming remain open. The expanding feature list now needs a more compact action layout so existing capabilities stay discoverable without overwhelming the tree.

## Feature-tree usability checkpoint

[Compact modeling actions](../examples/ai-cad/feature-actions/README.md) keep selection and existing-feature edits visible while disclosing new operations per solid. An actual three-part comparison reduced the tree from 1230 to 656 px and visible buttons from 28 to 8, with keyboard/accordion/redraw/preview-discard checks and unchanged native bytes. Menu-only interaction uploaded no GPU buffers; explicit full refresh uploaded once. This improves access to the existing bounded platform without changing model semantics.

## Exact dimension-entry checkpoint

[Decimal and unit entry](../examples/ai-cad/dimensions/README.md) accepts physical length strings in human and typed AI operations, with exact rational millimeter persistence. Mixed units survive preview, commit, reopen, native/STL download and undo; fixed/preserved values compare exact physical lengths. Native models and dimensionless/relationship literals retain the strict rational schema. General expressions and per-document display units remain open. Delivery of this checkpoint and compact feature actions is awaiting GitHub CI availability: hosted jobs report account payment/spending-limit failure before execution. Local validation is not a substitute for those merge checks. Continuing viewport navigation and broader platform work while those PRs remain reviewable.

## Viewport navigation checkpoint

[Standard views, pan and anchored zoom](../examples/ai-cad/navigation/README.md) add named orthographic views, pointer/keyboard navigation and consistent outside-face picking. Seven actual selections and63 WebGL/CPU projection configurations validate depth/coordinate agreement; camera changes reuse geometry buffers, while context restoration uploads once. No native model or exact geometry changes. CI remains blocked by account billing/spending limits; this checkpoint is reviewable work, not a merged release. Continue the next geometry dependency: full revolutions of planar radial profiles for turned parts, with an explicit supported-profile policy and independent validation. Preserve the open PR dependency chain.

## Full radial revolution checkpoint

[Editable profile revolutions](../examples/ai-cad/revolution/README.md) add full turns of rational radius/Z polygons, exact integral moments, analytic shared surfaces, browser/MCP edits and independent STEP comparisons. Axis-connected flat-ended parts and positive-radius rings support concave undercuts, translation, coordinate quarter-turns and linked instances. Partial turns, pointed apexes, arbitrary axes and curved Boolean intersections remain open. Continue into bounded swept-profile solids and broader sketch/assembly workflows; this checkpoint does not complete the platform.

## Straight profile sweep checkpoint

[Exact straight sweeps](../examples/ai-cad/straight-sweep/README.md) translate convex/concave XY sketches along parameter-backed XYZ vectors, with negative direction, exact moments, downstream planar cuts and source-linked placement. Browser/MCP create/edit/reject/undo and ten independent STEP comparisons verify the bounded operation. Curved paths, twist, varying sections and general curved intersections remain open. The next geometry dependency is exact coaxial intersection of supported analytic radial sections; arbitrary curved intersections still require a broader trimming and numerical policy.

## Coaxial curved intersection checkpoint

[Exact coaxial intersection](../examples/ai-cad/coaxial-intersection/README.md) clips convex radial sections of cylinders, frusta and revolutions, including rings, opposing coordinate-axis directions and source edits. Forty seeded taper pairs match independent piecewise disk integrals; twelve reference intersections match24 STEP readbacks and exact moments. Browser/MCP edit/reject/undo workflows are retained. Continue into bounded radial-section unions/differences and nonconvex sections; general noncoaxial curved trimming remains open.

## Coaxial material Boolean checkpoint

[Exact radial-section joins and cuts](../examples/ai-cad/coaxial-booleans/README.md) reuse the original planar-cell engine for convex/concave coaxial analytic sections, including stepped unions, blind recesses and through-bores. Browser/MCP editing, native history and14 independent reference solids/28 STEP readbacks are verified. Results with disconnected regions, contour holes or multiple axis contacts reject explicitly. Continue with CPU/memory/worker measurements on these broader geometry workloads before extending the representation to multiple contours and general curved trimming.

## Curved CPU workload checkpoint

[Isolated CPU/RSS and worker measurements](../examples/ai-cad/curved-runtime/README.md) cover 28 native workloads on Apple M4. Persistent transport reduces simple evaluation below 1 ms, while stepped unions still take about 52 ms. The next measured optimization target is the radial Boolean construction path: replace its temporary 3D cell work with exact 2D section boundaries while retaining independent material, manifold and export validation. No GPU geometry or general curved Boolean claim follows from these timings.

## Direct radial CPU optimization checkpoint

[Exact 2D section boundaries](../examples/ai-cad/direct-radial-runtime/README.md) replace temporary 3D construction cells in coaxial Booleans. On the same Apple M4, stepped-union evaluation changed from51.37 to0.43ms and nested cuts from46.32 to0.61ms; all28 benchmark replies remain identical. Independent cell boundaries, STEP material comparisons and saved browser/MCP/native workflows validate the change. General curved intersections and richer sketch/assembly constraints remain open.

## Concave coaxial intersection checkpoint

[Stepped and undercut common volume](../examples/ai-cad/concave-coaxial/README.md) extends the dedicated intersection feature through the direct exact radial engine, preserving the convex clipping path and recordings. Browser/MCP create, edit, invalid draft, undo and native/STL downloads agree; eight independent references and16 STEP readbacks cover concave pairs, conical walls, opposite axes and nested results. Separate radial regions and contour holes remain explicit limits.

## Coupled linear dimensions checkpoint

[Exact simultaneous linear constraints](../examples/ai-cad/linear-constraints/README.md)
compile coupled equalities into persistent affine relationships over explicit target
dimensions. Symbolic driver dependence survives ordinary edits, native reopen and
undo. Rank deficiency, contradictions and residual restrictions on free drivers
reject explicitly. The two-part browser/MCP workflow preserves a gap while solving
both widths and placement. Nonlinear sketch constraints and automatic choice of
degrees of freedom remain future work.

## Human constraint-authoring checkpoint

[Browser-authored coupled dimensions](../examples/ai-cad/linear-editor/README.md) expose explicit targets and structured equation terms through the shared native command. A failed rank check retains the draft for repair; saved formulas support driver edits, replacement and undo. Twelve actual requests, native snapshots and placed STL exports verify the workflow. General nonlinear sketch solving, persistent original constraint-row metadata and automatic target choice remain open.
