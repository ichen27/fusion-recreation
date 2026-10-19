# Editable model and command contract v1

## Model ownership

The authoritative model has `parameters` (ID → exact mm value string), ordered `features`, and `fixed` (parameter ID → invariant value). It stores intent; evaluated boundary geometry is regenerated. Feature IDs and parameter IDs survive dimension edits. One earlier block may feed one corner cut; a cut must reference a block directly, and only the terminal cut is displayed. Unsupported references and branches fail explicitly.

Block dimensions reference parameters: `{ "kind":"block", "id":"stock", "width":"width", "depth":"depth", "height":"thickness" }`.

Corner cut: `{ "kind":"corner_cut", "id":"corner", "input":"stock", "size":"corner_size" }`. For width W, depth D and setback S, it keeps `x+y <= W+D-S`. It removes a triangular prism of volume `S²H/2`. S must be positive and smaller than both W and D. This semantic anchor deliberately avoids naming a transient face index.

### Polygon profiles and extrusion (2026-10-19)

A profile is a separate editable feature on the XY plane:

```json
{"kind":"polygon_profile","id":"outline","vertices":[
  {"id":"origin","x":"zero","y":"zero"},
  {"id":"right","x":"width","y":"zero"},
  {"id":"top","x":"zero","y":"depth"}
]}
```

Each x/y field references a named parameter, including zero or negative coordinates; it is not a literal number or expression. Vertex IDs must be unique within their profile. The implicit closing edge joins the last vertex to the first; do not repeat the first vertex. There must be 3..32 vertices forming one **strictly convex** loop. Either winding is accepted. The exact interior-side test checks every vertex against every edge, rejecting crossings (including stars), concavity, repeated points and collinear corners. Coordinate magnitudes must be at most 1000000 mm. No tolerance-based cleanup is performed.

`{"kind":"extrude","id":"plate","profile":"outline","height":"thickness"}` references an earlier profile and a positive height parameter. It creates a solid from z=0 to z=height. Multiple extrusions may reference one profile; they are independent bodies, not a union. A profile may exist without an extrusion. Corner cuts still accept only blocks, not extrusions.

Parameter edits regenerate profiles and dependent solids together. A failed regeneration leaves the saved document unchanged. The saved model retains its input winding and vertex IDs; extrusion may reverse an internal copy to orient its boundary. Feature/parameter/vertex IDs are stable semantic references, but generated boundary indices are not persistent topology names. Coordinate edits use parameter operations. Structural edits use explicit `replace_feature` with the complete new vertex list; the existing browser sketch editor currently changes coordinates only.

Replies include `profiles` when at least one profile exists, containing `feature_id`, exact `area_mm2`, and `vertices` with `id` and `[x,y,z]` rational-string `position`. Empty `profiles` is omitted so existing recorded replies replay unchanged. The viewer renders unextruded outlines and terminal solids; profile measurements remain available after extrusion. Schema version remains 1 for this additive feature extension. Older binaries cannot open documents containing the new feature kinds; upgrade the engine and MCP adapter together and restart clients to reload tool schemas.

[Runnable example and saved stages](../examples/ai-cad/profile-extrusion/README.md).

Every block, convex polygon extrusion and corner cut passes the custom kernel's closed-boundary, orientation, manifold and convexity checks. Fixed values are checked against exact rational values, independently of AI interpretation. A language model can still misunderstand intent; the tool descriptions, preview, preserved parameters and explicit constraints make that inspectable, not infallible.

## Exact parameter relationships

Optional `model.relations` maps an existing parameter ID to an affine relationship:

```json
{"tip_x":{"offset_mm":"0","terms":{"width":"1/2"}}}
```

This means `tip_x = 0 mm + (1/2 × width)`. Coefficients are dimensionless exact rational strings; inputs and offsets are in mm. Up to eight nonzero terms are allowed per relationship. Empty terms define a constant. General expressions, products of dimensional parameters, trigonometry and a geometric constraint solver are not supported.

`set_relation` takes `id, relation` and explicitly creates/replaces a relationship. Define its target parameter first. `remove_relation` takes `id`, evaluates the current dependencies, removes the rule and retains the computed value as an independent parameter. It does not release a fixed constraint. Direct `set_parameter` or `adjust_parameter` on a derived target fails with `derived_parameter`; edit an input or the rule, or remove the rule first.

All dependent values refresh after a batch before preserve/fixed/geometry validation. `fix_parameter` and `remove_relation` also refresh at their position in the ordered operation sequence, so they capture the current computed value. Relationships may refer to other derived parameters. Cycles reject with a dependency path; missing references reject explicitly. Resolution is bounded to 64 total parameters/relationships, eight terms per rule, and 128-bit numerators/denominators for coefficients, intermediate products/sums and results. Terms evaluate in parameter-ID order. An oversized intermediate rejects even if later terms could cancel it.

Derived values remain present in `model.parameters` for inspection. They are checked against their rules when a saved/input model is loaded; mismatched values reject with `relation_mismatch` rather than silently repairing the file. The host persists the updated values and rules together. `changed_parameters` includes changed dependent values. A fixed derived parameter constrains upstream edits; preserve also applies to derived values when explicitly listed. To widen a symmetric profile, preserve its unrelated independent dimensions, not the center coordinate that should move with width.

The browser displays a derived field and its formula, disables direct edits, and automatically excludes dependent fields from its default preserve list. Fixed invariants remain enforced by Rust. Rule creation/replacement/removal currently uses CLI/MCP; there is no graphical relationship editor yet.

Empty relationships are omitted on output; old fixtures replay unchanged. This is an additive schema-v1 extension. Older engines reject documents with relationships; update engine and adapter together and restart connected clients to refresh tool schemas.

[Symmetric-profile example](../examples/ai-cad/relationships/README.md).

## Commands

All fields shown below are mandatory; unknown fields are rejected.

| Action | Other fields | Behavior |
|---|---|---|
| `inspect` | none | Current model, geometry, revision, undo/redo availability |
| `preview` | `expected_revision`, `operations`, `preserve` | Evaluates without saving, changing history, or advancing revision |
| `commit` | `expected_revision`, `transaction_id`, `operations`, `preserve` | Validates and atomically publishes a complete edit |
| `preview_import` | `expected_revision`, `document` | Validates a native envelope and previews replacing the model |
| `import` | `expected_revision`, `transaction_id`, `document` | Replaces the model as one undoable workspace edit; source history is not copied |
| `undo`, `redo` | `expected_revision`, `transaction_id` | Reverses one edit and advances revision |

Operations are tagged with `op`: `define_parameter`/`set_parameter` take `id, mm`; `adjust_parameter` takes `id, delta_mm`; `add_feature` takes `feature`; `fix_parameter`/`release_parameter` take `id`. Fixing an already-fixed parameter keeps its existing invariant. Changing it requires an explicit release. `preserve` contains existing parameter IDs that must have equal exact values before/after the entire batch, even if a constraint is released.

A successful command returns `result`, including `schema_version:1`, `units:"mm"`, `revision`, `model`, `bodies`, `changed_parameters`, `can_undo`, `can_redo`. Each body carries `feature_id`, the shared boundary schema and exact `volume_mm3`. Preview returns `preview:true`; mutation returns `committed_revision` and `replayed`.

Retries are checked before revision preconditions: an identical transaction ID and canonical request hash acknowledges the original `committed_revision` and returns the **current** model/revision, with `replayed:true`. Reusing an ID for another request gives `transaction_conflict`. A new edit against stale state gives `revision_conflict`; inspect and replan, never blindly update the expected revision.

## Storage

A POSIX advisory lock serializes cooperating host processes using a permanent sibling `.lock` file. Locks release when the process exits. The host reads/checks the snapshot, validates current/history models through Rust, executes the command and writes a complete envelope to a same-directory temporary file. It fsyncs the file, atomically replaces the destination, then fsyncs its parent directory.

Failure before replace returns `save_failed`, leaving the prior snapshot intact. Failure after replace returns `commit_uncertain`: inspect and retry the **identical** transaction. An envelope SHA-256 detects accidental corruption; invalid files are rejected rather than overwritten. Editing snapshots outside the host is unsupported. The native C++ journal/locking code is not reused or implicitly certified by these tests.

Limits: 64 parameters, 32 features, 64 fixed constraints, 128 operations/request, 64 preserve IDs; 128-bit rational numerator/denominator inputs; geometry dimension `(0, 1000000]` mm; 256 KiB ordinary host command (native import permits 16 MiB plus 1024 bytes of command framing), 1 MiB Rust input, 16 MiB saved envelope; 64 undo/redo snapshots and 1024 receipts. Revision is bounded to JavaScript's exact integer range. No-op commits fail and do not advance revision. New commits after undo clear redo.

## Diagnostics and repair

Errors carry `code`, `entity`, `message`. Typical codes: `missing_parameter`, `duplicate_id`, `invalid_number`, `dimension_range`, `cut_range`, `invalid_profile`, `profile_limit`, `coordinate_range`, `unsupported_reference`, `constraint_conflict`, `preserve_conflict`, `revision_conflict`, `transaction_conflict`, `invalid_document`, `commit_uncertain`, `derived_parameter`, `relation_cycle`, `relation_mismatch`, `relation_overflow`, `relation_limit`, `invalid_relation`, `missing_relation`. No failed validation partially changes the model. Agents should repair the identified parameter/reference or ask for an intent decision; unsupported geometry must not be substituted silently.

## Analytic through-holes and exports (2026-10-19)

```json
{"kind":"through_holes","id":"bracket","input":"plate","holes":[
  {"id":"mount","x":"hole_x","y":"hole_y","radius":"hole_radius"}
]}
```

`input` must reference an earlier polygon extrusion (convex or simple concave) or cylinder. One group of 1..16 uniquely named holes per extrusion is supported; the consumed extrusion is hidden. Centers and radii reference exact mm parameters. All holes run along +Z through the full height. Circles must be strictly inside the outer loop with positive distance from every boundary segment and mutually separate; touching, intersecting and breakout reject. Blind holes use the separate depth-aware feature below. Radius is positive and at most 1000000 mm. The original profile IDs and hole IDs remain stable through coordinate edits.

The exact predicate uses ray-crossing containment and squared distance to each finite boundary segment (including endpoint distance when the projection is outside the segment); circle pairs require `squared_center_distance > (r1+r2)^2`. No square roots, π approximations or tolerance decisions enter these predicates. The bounded constructive representation guarantees a single perforated-prism family; it does **not** pass through or claim the convex planar B-rep validator. A general curved B-rep/incidence model remains future work.

Analytic bodies omit `boundary` and include `analytic: {kind:"perforated_prism", outer, height, holes, volume}`. The outer loop is counterclockwise rational XY coordinates; caps lie at z=0 and z=height, inner cap loops are circles, and cylinder walls point into the holes. `volume` is `{constant_mm3, pi_subtract_mm3}` with exact rational strings, meaning `constant − pi_subtract * π`. `volume_mm3` is a human-readable symbolic string for these bodies, not parseable as a rational. Old planar body replies remain unchanged. Consumers must branch on representation. Upgrade engine, viewer and MCP adapter together; old binaries cannot load the new feature.

`model-engine --mesh` takes `{model, feature_id, segments}` and returns disposable float64 vertices, triangles, boundary display edges and `max_radial_error_mm`. Segment count is 16..256. The model is validated first. Earcut triangulates the sampled cap rings; closed opposite edge incidence and noncollapsed triangles are checked. Float failure returns `tessellation_failed` independently of model validity. This is not a general self-intersection proof. The error bound is the chord sagitta, excluding floating-point rounding.

Only HTTP display replies add `display_mesh`, `volume_approx_mm3` or `display_error` to analytic bodies. A failed display must not turn a successful commit into an apparent failed commit. Saved snapshots, CLI and MCP retain the exact representation. STL download selects a saved revision, terminal body and segment count; pending previews cannot be exported through the browser. The read-only CLI supports STL and optional STEP, with exclusive output creation. It snapshots and validates the requested revision before translating; subsequent concurrent edits do not change that snapshot. Neither export retains parametric history. [Runnable exports and artifacts](../examples/ai-cad/bracket/README.md).

## Process-local reuse

The host may reuse successful no-operation evaluation of identical model content under the same engine file identity. It still reads and verifies every document envelope and validates all current/history contents, using a bounded 128-entry/8 MiB encoded-result cache per Store. A changed or missing engine bypasses previous results. Every edit and preserve precondition still passes through Rust. HTTP mesh reuse has a separate 32-entry/16 MiB bound; neither cache is persisted. JSON decoding prevents caller mutation of cached data. [Measurements and exact limits](../examples/ai-cad/runtime/README.md).

## Simple concave planar profiles

`planar_profile` uses the same named-vertex schema as `polygon_profile` but accepts one simple straight-edge XY loop, including inward corners. It retains the 3..32 vertex and coordinate bounds. Exact predicates reject repeated or touching vertices, zero edges, collinear corners, crossings and overlapping nonadjacent edges; both windings are accepted. The original `polygon_profile` remains strictly convex so existing documents and failure semantics are preserved. No automatic topology repair or migration is performed.

A positive-Z extrusion of `planar_profile` produces an analytic `polygon_prism` with a counterclockwise rational outer loop, height, empty holes and exact volume coefficients (`pi_subtract_mm3 = "0"`). Its `volume_mm3` is rational. Adding a through-hole group produces the existing `perforated_prism` representation. These constructive shapes do not claim to pass the convex B-rep validator. Render/export consumers must accept both analytic kinds; meshes remain derived approximations. This does not implement general nonconvex Boolean operations, arbitrary profile planes, multiple outline loops, spline edges or persistent generated-face names.

New browser sketches use `planar_profile`. Editing an existing convex profile preserves its original kind and restrictions. [Commands, editable snapshots, STEP/STL and independent validation](../examples/ai-cad/concave-profile/README.md).

## Structural edits

- `replace_feature`: `{op:"replace_feature", id, feature}` replaces the complete definition in its existing timeline position. The replacement must retain the ID and feature kind. Named vertex/hole IDs supplied by the caller are preserved; removing an item explicitly removes that semantic reference. Retain surviving IDs when changing topology. Definitions still reference earlier features, and the whole model regenerates before acceptance. This supports changing profile vertices, hole lists and feature parameter references; it does not stabilize generated face indices.
- `remove_feature`: `{op:"remove_feature", id}` removes exactly one existing feature. No dependency cascade or parameter deletion is implied. Explicitly repair/remove downstream references in the same atomic batch; feature removals can be listed in either order because final geometry is checked after all operations. Removing a through-hole group reveals its parent extrusion.
- `remove_parameter`: `{op:"remove_parameter", id}` deletes an existing parameter. First release its fixed constraint and remove its own relationship if present. Remaining geometry, relationships and preserve preconditions must still resolve. Remove dependent relationships before removing their sources. Deletion does not silently rewrite constraints. `changed_parameters` includes deleted IDs; look up values only if the ID remains in the returned model.

Feature replacement rejects ID/kind changes with `feature_identity`; missing targets reject with `missing_feature`/`missing_parameter`. A fixed or derived parameter cannot be removed directly (`parameter_in_use`). Invalid dependent references retain existing `unsupported_reference`/`missing_parameter` diagnostics. All failures leave saved state and history unchanged. A complete transaction can define new coordinates, replace an existing feature and remove now-unused parameters. Parameter/feature count limits apply to the resulting model. New operation schemas require restarting MCP clients; persisted model schema remains unchanged.

[Actual browser addition/removal, exact native snapshots, explicit cleanup and replay](../examples/ai-cad/feature-edits/README.md). Browser hole editing supports adding/removing individual circles; clearing a group previews removal of its feature. It retains unused parameters so shared references and constraints are never deleted implicitly. CLI/MCP `remove_parameter` handles explicit cleanup.

## Browser edge relationships

The sketch editor maps an oriented edge start→end to existing affine operations: horizontal sets `end.y = start.y`, vertical sets `end.x = start.x`. A shared parameter reference already satisfies the link and creates no self-dependency. Fixed targets refuse new links; an existing different relationship must be cleared explicitly. New targets are excluded from preview `preserve` because their values may change. Clearing an existing relation runs before direct coordinate edits, so the relation's last evaluated value can be retained or explicitly changed.

This is a directed dependency editor, not a simultaneous geometric solver: it does not infer degrees of freedom, minimally solve redundant constraints or reverse dependency direction when dragging a driven coordinate. Cycles use the Rust dependency-path error. Draft relationships rebuild at preview, while saved model coordinates remain authoritative. Removing a point from a new unsaved drawing drops only draft links involving the removed coordinates; starting a fresh rectangle clears its draft links. Existing sketch topology is unchanged by this editor.

## Circular stock and flanges

`{kind:"cylinder",id,x,y,radius,height}` defines a true circular outer boundary, centered at the referenced x/y parameters, from z=0 to the positive referenced height. Center magnitudes are at most1000000 mm; radius/height are positive and at most1000000 mm. Through-hole groups can consume cylinders with the same one-group,1..16-hole limit. A hole center distance `d` and radius `r` must satisfy `R-r > 0` and `d² < (R-r)²`; pair separation remains exact. No square roots or tolerance classification enter native validation.

These bodies use `analytic.kind = "round_prism"` with `outer_circle: {center:[x,y],radius}` instead of polygon `outer`. Height and `holes` have the existing meanings. Exactly one outer representation is constructed internally. Structured volume keeps the existing `constant_mm3 − pi_subtract_mm3 × π` convention: round stock has constant0 and a **negative** subtraction coefficient. Human-readable `volume_mm3` is `coefficient*pi`. Consumers must use the structured volume or representation rather than parse the human label as a rational. Existing polygon replies remain unchanged.

Display/STL sample the circular outer boundary counterclockwise and holes clockwise, and report the largest radial chord error across all circles. For circular stock, complete hole disks must fit inside the outer tessellation's incircle with a floating-point margin; hole pairs also need representable separation. Valid exact models with smaller clearances can refuse display/STL at a chosen segment count. This conservative refusal protects against tessellation crossing the outer boundary. STEP translates circular wires and cylindrical walls and requires radius/height/clearances above1e−6 mm. It performs no solid subtraction in the exporter; the independent validation oracle does.

Cylinder creation uses CLI/MCP; its dimensions and holes can be edited in the viewer, whose hole dialog shows the circular boundary. There is no general circle sketch/revolve, arbitrary axis, fillet or curved intersection solver in this addition. [Editable flange examples, browser recording, STEP/STL and independent checks](../examples/ai-cad/round-flange/README.md).

Round-stock tessellation tries the original angular samples and, only if validation fails, at most two deterministic phase offsets. This addresses collinear triangulation bridge triangles for aligned circles. Circle radii, centers, segment count and maximum chord-error bound stay unchanged; every candidate must pass containment, noncollapsed-triangle and opposite-edge-incidence checks. All six hole orders at16/64/128 segments are covered for the radius12 bore regression. Native geometry is never changed by this display retry.


## Flat-bottom blind holes

`{kind:"blind_holes",id,input,depth,holes}` has the same stock and named circle references as `through_holes`, plus a depth parameter. Require `0 < depth < stock height` exactly. Holes descend from the top face and end at `height − depth`; all holes in the group share this depth. One hole group consumes a stock feature. Switching kind requires explicit removal/recreation because `replace_feature` preserves kind.

The existing analytic prism representation gains optional `hole_depth`. Its absence retains full-depth through-hole behavior. With depth present, the bottom stock face is unperforated, each inner cylinder spans `height-depth` to `height`, and each circular floor has an upward material normal. Removed volume is `π × sum(radius²) × depth`. Circle containment/separation rules and IDs are unchanged. Old serialized replies remain unchanged.

Display/STL construct separate outer bottom and pocket floor faces. Numerically collapsed depth or floor rejects tessellation without invalidating the exact model. STEP explicitly translates these faces and walls; both depth and remaining floor must exceed 1e−6 mm. [Independent surface, floor-containment, volume and browser evidence](../examples/ai-cad/blind-holes/README.md). This does not provide drill-tip cones, counterbores, mixed-depth groups, intersecting pockets, arbitrary axes or features on already perforated stock.

## Convex arbitrary-plane cuts

`{kind:"plane_cut",id,input,normal:[nx,ny,nz],offset}` retains `nx*x + ny*y + nz*z <= parameter(offset)`. Normal components are dimensionless rational literals, not parameter references, and must not all be zero. Offset references an existing mm parameter and is not necessarily perpendicular distance. The input can be a block, convex profile extrusion, corner cut, or a previous planar Boolean, rigid transform or plane-cut result. Nonconvex results use the backing-cell path described below. Initial simple-profile extrusions use exact convex validation or concave decomposition as described below. Analytic circular/perforated stock rejects explicitly. Each input can have one consuming feature; subsequent cuts reference the preceding cut.

Cuts retain the existing planar `boundary` representation, exact rational vertices and volume. Empty or lower-dimensional results return `empty_solid`; unchanged cuts remain valid features. Parameters, previews, transactions, undo and feature replacement retain existing semantics. Generated face/edge indices are not persistent references. The original boundary kernel enforces its existing 128-vertex/128-face/384-edge and 1024-bit component bounds. [Browser and independent STEP/STL acceptance evidence](../examples/ai-cad/plane-cuts/README.md).

## Multi-body STL archives

The loopback viewer's read-only `GET /api/export.zip?revision=N&segments=S` exports every terminal solid from one validated saved snapshot. A later concurrent edit cannot mix revisions among its files. Single-body `/api/export.stl` remains supported. The ZIP contains numerically prefixed STL filenames and `manifest.json` with revision, mm units, circle segment count, feature/file mapping, exact source volumes, triangle counts and maximum radial chord error. Prefixes avoid case-folded filename collisions. No native history is embedded. Empty documents, stale revisions, failed tessellation or more than 64 MiB of uncompressed STL reject the entire archive. The browser uses one ZIP download when multiple solids are saved.

## Native file workflow

`GET /api/export.cad?revision=N` returns a locked, validated native snapshot with complete history and receipts; a stale revision rejects. `preview_import` and `import` accept this envelope as `document`. Both validate every source history model and checksum. Import retains the destination revision/receipts, adds its prior model to undo and clears redo. Source history/receipts are not copied. Existing fixed/relationship constraints belong to the imported model; replacement is explicit rather than a constrained dimension edit. The browser labels this action **Replace model**. Reopen a downloaded file as the host store to retain that file’s full history. [Recorded acceptance and portable artifacts](../examples/ai-cad/native-project/README.md). These commands are available through the document host/HTTP API; no new MCP import tool is exposed.

## Plane cuts on browser sketches

A plane cut can consume an unperforated `planar_profile` extrusion with a validated simple outline. Convex outlines use the existing boundary path; concave outlines use exact decomposition. Source sketch/prism representation stays unchanged. Upstream edits rebuild dependent cuts and invalid/simple-profile violations reject atomically. [Historical browser evidence](../examples/ai-cad/sketch-plane/README.md) preserves the former concavity rejection; [current concave workflow](../examples/ai-cad/concave-operations/README.md) verifies acceptance.


## Convex solid intersection

`{kind:"intersection",id,left,right}` keeps the common positive volume of two distinct earlier convex planar bodies. It consumes both inputs. Previous cuts/intersections and convex simple-profile extrusions are supported; circular/perforated/concave operands reject with `unsupported_reference`. Identical geometry is valid under distinct feature IDs. Same-ID operands reject `invalid_intersection`; reused consumed inputs reject `unsupported_branch`. Disjoint or touching-only solids reject `empty_solid`, including on upstream edits. No partial result is committed.

Each outward face of the second operand supplies an exact clipping half-space. Every intermediate passes the original closed-convex boundary validator and its resource bounds. The result has exact planar `boundary` and rational `volume_mm3`, and can feed subsequent cuts/intersections. Operation order may affect generated topology indices, which are not persistent references. Existing feature replacement/removal, parameter constraints and transaction semantics apply. [Browser, MCP, native, STEP/STL validation](../examples/ai-cad/intersection/README.md). Use the newer `boolean` feature below for planar union/difference and nonconvex results; curved Booleans remain unsupported.

## Exact planar translation

`{kind:"translate",id,input,offset:[dx,dy,dz]}` moves an earlier convex planar body or a previous planar Boolean/rigid result by global XYZ offsets. Each offset is a parameter reference in mm, bounded to ±1000000 per component (`translation_range` on violation). It consumes its input and returns an exact planar boundary with unchanged volume. Vertices receive the offset; each face equation `n·p=d` becomes `n·p=d+n·offset`. The original closed-convex boundary validator checks the result and rational resource limits. Fixed/derived/shared parameters and undo/transaction behavior remain unchanged.

Convex sketch extrusions, blocks, cuts, intersections and earlier translations are supported. Previous planar Boolean/rigid/cut results are also supported, including nonconvex geometry. Initial simple concave extrusions and analytic circular/perforated stock are supported by the exact paths described below; no implicit geometry approximation is introduced. Downstream plane offsets remain global coordinates. A movement invalidating a downstream intersection rejects atomically. [Native/browser/MCP/STEP/STL acceptance](../examples/ai-cad/translation/README.md).

## Exact quarter-turn rotation

`{kind:"rotate_quarter",id,input,axis:"x|y|z",turns:1|2|3,pivot:[px,py,pz]}` consumes an earlier convex planar solid or a previous planar Boolean/rigid result. Positive turns use the right-hand rule. Pivot references resolve to mm values bounded to ±1000000; invalid turns or pivot range return `rotation_range`. Invalid axes reject during decoding. Fixed/derived/shared parameters retain existing behavior.

For exact signed-permutation matrix R and pivot c, points become `R p + c - R c`. Normals become `R n`, and face offsets become `d + (R n)·(c - R c)`. Original convex-boundary validation checks the result and computed-rational limits. Dimensions/volume remain exact; no trigonometric approximation is stored. Downstream global-coordinate cuts/intersections rebuild atomically. Supported inputs match translation, including prior quarter turns. Arbitrary angles, analytic curved inputs, initial concave extrusions and component instances remain unsupported. [Browser/native/MCP/STEP/STL evidence](../examples/ai-cad/quarter-turn/README.md).

## Shared workspace selection

Selection is separate from modeling commands and native history. `GET /api/context` / MCP `cad_context` returns `{revision, selection_status, selected_body, model}` from one document lock. Status is `current`, `empty` or `stale`; only current context includes a selected body. `POST /api/selection` accepts exactly `{action:"select",expected_revision,feature_id}`; null clears. Only terminal saved solids are selectable. Invalid/stale requests leave context unchanged.

A bounded atomic sidecar records schema 1, revision, complete saved-state SHA-256 and nullable feature ID. Both revision and content must match when resolving context. The full native file remains unchanged; no history/receipt is created. Sidecar corruption reports `invalid_selection` without blocking model edits, and clear/reselect repairs it. All selection writes serialize with model edits through the existing document lock. This is one shared local selection, not multi-user presence or an authorization grant. Within one browser clicks queue in order; multiple clients use latest successful selection. Preview geometry is never published. An AI edit still supplies explicit operations and current expected_revision. [Actual browser/MCP evidence](../examples/ai-cad/shared-selection/README.md).

## Feature and parameter explanations

Rust `--explain` validates `{model,feature_id}` and returns the selected feature's explicit source graph and potential downstream impact. Its exhaustive feature match distinguishes feature references, parameter references and literal values (for example, plane normals and rotation axes are not parameters). Source features retain declaration order. Parameter closure follows bounded affine relationships; root driving parameters can be fixed, and direct editability excludes fixed or derived values.

For each relevant parameter, affected parameters/features/terminal bodies are computed across the entire model, including shared consumers outside the selected source chain. This is conservative dependency reachability, not a proof of numerical sensitivity or successful geometry. `cad_explain` and `POST /api/explain` take exactly `{expected_revision,feature_id}`, read under the document lock and never mutate native history/selection. Stale revisions reject. [Recorded browser/MCP workflow](../examples/ai-cad/model-intent/README.md) verifies that a shared width changes both parts while height stays fixed.

## Browser preview jobs

`POST /api/preview-jobs` accepts the existing strict preview command and returns `{job_id,status,revision}`. `GET /api/preview-jobs?id=<id>` reads status; terminal jobs include `reply` in the ordinary result/error envelope. `POST` with exactly `{action:"cancel",job_id}` requests cancellation. States are queued, running, cancelling, succeeded, failed and cancelled. Completed cancellation is idempotent; the browser also discards a finished result if cancellation was requested before it was displayed. Unknown/evicted jobs return `missing_job`.

A locked saved snapshot is encoded once; the worker receives no store path and releases no model mutations. One CPU worker per viewer, four outstanding snapshots, 30-second parent/worker deadlines, 32 completed records and 8 MiB retained results bound the runtime. Cancellation kills/reaps the isolated process group. Existing expected_revision checks remain the commit gate; a snapshot can finish after another client edits, but cannot silently commit over it. Loopback host/origin policy also covers job submission, polling and cancellation. Queue metadata is ephemeral and not included in native files. [Actual browser and process evidence](../examples/ai-cad/preview-jobs/README.md).

## Planar solid Booleans

`{"kind":"boolean","id":"combined","left":"stock","right":"tool","operation":"difference"}` computes `left - right`. Other operations are `union` and `intersection`. Both distinct earlier terminal operands are consumed. Inputs can be convex planar bodies accepted by the existing convex helper or previous Boolean results. Simple concave profile extrusions are supported. Analytic circular/perforated bodies reject; they are not approximated as polyhedra. Subsequent Booleans accept previous nonconvex, holed, cavity and disconnected results. Empty/lower-dimensional results reject with `empty_solid`. An unchanged positive-volume result is allowed.

The original Rust core decomposes these operations into disjoint-interior convex cells using exact rational half-space clipping. It subtracts opposing coplanar patches, cancels internal seams and forms consistently oriented outer/inner face loops. Validation checks two opposite uses per edge, a connected cyclic vertex link, orientable shell Euler characteristic, positive signed volume and exact equality with backing-cell volume. It is a validator for internally constructed results, not arbitrary imported boundary data. Point/edge-only joins reject with `invalid_polyhedron`; full-face joins are supported.

A Boolean body returns `boundary`, rational `volume_mm3`, and `components`, a partition of face indices by connected material component. One component may contain both an outer shell and cavity shells. A body may contain multiple disconnected material components. These indices are disposable and are not persistent selection references. Backing cells are regenerated from typed history and are not serialized into documents. Legacy convex intersection requires a convex merged boundary. Exact movement, quarter turns and plane cuts also accept nonconvex Boolean results as described below.

Per-result/subdivision limits: 32 cells, 256 total cell faces, 512 exposed patches, 512 merged vertices, 256 merged faces, 1024 merged edges, 8192 patch points per subdivision/group, and 8192 directed planar subdivision edges per group. Computed coordinate/plane rational components are bounded to 1024 bits; user literals retain the 128-bit input limit. Limits can reject an otherwise valid solid, and these are bounded initial capabilities rather than a scalability claim. Existing process timeouts/cancellable preview jobs also apply.

The disposable float64 mesh projects each face onto a coordinate plane, triangulates outer/inner loops and validates triangle incidence. A failed float mesh leaves the exact saved body valid. STEP only translates/sews the supplied faces and component shells, then verifies validity, component count and volume after readback; its 1e-7 mm adapter tolerance does not change exact native geometry. STL has no native parameter/history data and may contain multiple closed shells.

Browser creation, operation replacement, upstream regeneration, MCP schemas, exact seeded volumes, contact rejection, native undo/reopen and independent STEP Boolean comparisons are covered by [retained artifacts](../examples/ai-cad/planar-booleans/README.md).

## Rigid transforms of planar Boolean results

`translate` and `rotate_quarter` also accept a previous planar Boolean result or its rigid transforms. Each backing convex cell undergoes the original exact operation; the merged boundary, face holes and component membership are regenerated. Volume and material-component count must remain equal. This retains the cells needed for later Boolean operations rather than keeping only a display mesh. The same feature IDs, parameter references, ±1000000 mm offset/pivot limits and single-consumer rules apply.

Whole results move together, including all cavity shells and disconnected pieces. Individual component instances and assembly joints are not introduced. Simple concave extrusions are supported. Analytic curved/perforated stock now supports rigid placement as described below; arbitrary-angle rotations remain unsupported. Legacy `intersection` still requires convexity; use `boolean` for a subsequent intersection of a nonconvex transformed result. Plane cuts also support nonconvex results as described below.

[Recorded browser/MCP transforms and independent STEP results](../examples/ai-cad/planar-transforms/README.md) cover moved/turned through-holes, cavities and split solids, exact fractional pivots/all quarter turns, downstream Boolean reuse, upstream dimension edits, range rejection and undo.

## Plane cuts of nonconvex planar results

`plane_cut` now accepts prior planar Boolean results, their exact rigid transforms and previous cuts of those results. Each backing cell is clipped by the exact half-space `normal · position <= offset`; empty/lower-dimensional cells are discarded. Remaining cells regenerate the complete merged boundary, including face holes and material-component membership. The whole result must retain positive volume. A cut may open an internal cavity, open a through-hole at the side, split a connected shape or remove whole disconnected pieces. Subsequent transforms and Booleans retain backing cells.

The existing rational normal/parameter-backed offset, zero-normal rejection, single-consumer/history behavior and resource limits remain unchanged. Native state is atomic on empty/nonmanifold/limit failure. Circular analytic stock, curved hole groups and arbitrary imported boundary data remain unsupported. Legacy convex-only `intersection` is unchanged; use `boolean` for nonconvex intersections.

[Native browser/MCP history, pocket STL and eight independent STEP cases](../examples/ai-cad/nonconvex-plane-cuts/README.md) cover topology changes, oblique cuts, moved/turned inputs, empty-result rejection and undo. Exact seeded central planes split a symmetric cavity into equal-volume halves.

## Simple concave extrusion inputs

Boolean, translation, quarter-turn and plane-cut operations accept validated unperforated simple `planar_profile` extrusions. Rational ear clipping normalizes winding, uses exact inclusive orientation/containment predicates, checks positive triangle areas and exact summed area, and constructs validated disjoint triangular prisms. The 32-vertex profile limit yields at most 30 initial cells; existing cell/patch/rational limits still bound subsequent operations. Convex inputs retain their existing serialization; unconsumed concave extrusions retain their analytic prism representation. Generated backing cells are rebuilt from source history. Legacy `intersection` remains convex-only. Circular stock and analytic hole groups are not tessellated into native polyhedra.

[Retained evidence](../examples/ai-cad/concave-operations/README.md) covers both windings, 32 vertices, tiny rational geometry, topology splitting, browser/MCP history and independent STEP residuals.

## Linked planar instances

`{"kind":"instance","id":"copy","source":"part","offset":["copy.x","copy.y","copy.z"]}` creates a non-consuming translated placement of an earlier supported planar solid. Offsets reference parameters in millimeters, each within ±1000000. Exact volume/component count are preserved. Multiple/nested copies follow source dimensions; offset edits affect only that placement and its dependents. Source removal must explicitly remove or repair dependents in the same transaction. Forward/self references reject. The source may be an earlier consumed historical solid; it refers to that precise feature stage, not the final result of later consuming features.

Instances keep backing cells for subsequent planar operations and participate in provenance/impact, picking, native history and separate world-coordinate exports. Source references do not consume a solid; ordinary downstream operations still do. Browser creation selects terminal supported bodies, exposes separate edit/copy actions and preserves source dimensions. Analytic circular/perforated stock now supports linked placement as described below. Model/cell limits still apply; per-instance geometry is currently rebuilt and expanded in display/export data, with no GPU instancing performance claim. Separate overlapping bodies are not automatically fused or collision-checked. External documents, materials, assembly joints and configurations remain open.

[Recorded workflow and independent comparisons](../examples/ai-cad/linked-instances/README.md) include source edits, nested placement, nonconvex topology, atomic rejection, undo/reopen and five STEP references.

## Exact planar measurements

The engine `--measure` request is `{"model":...,"feature_id":"part"}`. HTTP `POST /api/measure` and MCP `cad_measure` accept `expected_revision` and `feature_id`, validate a terminal solid and return read-only `revision`, `feature_id`, `volume_mm3`, `bounds_mm:[minimum,maximum]`, `centroid_mm` and `centroidal_volume_inertia_mm5`. Values are exact arithmetic strings, axes are global XYZ. Planar values are rational; analytic circular/perforated measurements can contain rational functions of pi as specified below. The symmetric tensor is ∫((r·r)I−rrᵀ)dV relative to the volume centroid, in mm⁵. It assumes uniform density only when interpreting centroid as center of mass; multiply by specified density for physical inertia. No density/mass is assigned.

Validated boundary loops integrate as oriented signed tetrahedral chains, including concave/inner loops and cavity shells. Initial unperforated profile extrusions use their exact planar boundary. Circular analytic stock and circular hole groups use symbolic pi integration as specified below. Integrated volume must exactly match validated geometry; moment rationals are bounded to 8192 bits. HTTP input is ≤4096 bytes, engine request ≤1 MiB, and subprocess timeout 20 seconds. The bounded content/executable-keyed host cache reuses exact replies; requests hold the document lock for a consistent revision. UI measurements clear on selection/revision changes and stale replies are discarded. No surface-area, clearance, collision, principal-axis or cross-body union claim is made. [Closed-form, recorded and independent evidence](../examples/ai-cad/measurements/README.md).

## Analytic rigid placement

`translate`, `rotate_quarter` and `instance` now also accept circular stock and original through/blind-hole groups. The analytic result retains local geometry and adds optional `placement:{axes:[[...],[...],[...]],origin:[...]}`. Axes are rows of a proper signed-permutation matrix; origin values are exact rational strings. World coordinates equal axes times local coordinates plus origin. Quarter turns compose around the global parameter-backed pivot. Translation composes global offsets. Identity results may retain an explicit identity placement. Existing unplaced analytic and planar result serialization stays unchanged.

Placement is constructed internally from typed history, not accepted as arbitrary model input. Input offsets/pivots retain ±1000000 limits and composed-origin rationals are bounded to 1024 bits. Exact symbolic volume and source hole dimensions are unchanged by placement. Mesh/STL applies the rigid transform before checking floating topology, preserving the radial approximation bound. STEP constructs analytic surfaces then transforms them and rechecks validity/volume. Native cuts/Booleans still reject analytic curved placements; measurements support them via symbolic pi integration; hole groups must be edited at their original source stage. Arbitrary rotations, scale/mirror and curved intersections remain open. [Recorded evidence and independent analytic references](../examples/ai-cad/analytic-placement/README.md).

## Symbolic analytic measurements

The same measurement interfaces accept every current analytic prism family, with optional exact placement. Bounds are rational. Centroid/tensor entries are exact arithmetic strings with integer literals, parentheses, `+`, `-`, `*`, `/` and `pi`; coefficients can be fractions. These expressions are outputs only: parameter literals remain bounded rational numbers. Volume retains its existing exact symbolic string. Existing planar measurement output is unchanged.

Polygon moment formulas and exact circular-cylinder subtraction yield linear-in-pi volume/first/raw-second moments. Centered moments have at most quadratic-in-pi numerator over linear volume; exact polynomial division simplifies cancellable factors. Coefficients and division intermediates obey the 8192-bit measurement budget. Native geometry validation ensures the volume denominator is nonzero; the integrated constant/pi coefficients must exactly equal native volume coefficients. Rigid placements transform centroids/bounds and apply R I Rᵀ to centroidal inertia. No approximate pi is used by the engine. Existing uniform-density interpretation, read-only revision checks, host cache and time limits remain unchanged. [Exact identities, browser/MCP edits and fifteen independent references](../examples/ai-cad/analytic-measurements/README.md).

## Request-local geometry reuse

Original-model geometry is always validated before applying operations. After relations refresh and preserve checks, the evaluator retains the longest unchanged feature prefix, requiring identical feature definitions and identical referenced parameter values. It moves original intermediate profiles/bodies/cells into the new evaluation and rebuilds the remaining suffix. Consumption checkpoints preserve terminal-body and branching semantics, including when consumers are removed. Global model/parameter/relation/fixed checks run again even if the entire geometry prefix is reused. No output/schema fields change.

This state is private to one engine invocation and never supplied by clients or loaded as trusted persisted geometry. Existing per-model limits bound retained intermediates; 33 consumption checkpoints of at most 32 IDs bound additional bookkeeping. A changed root can still require a full second geometry pass. Cross-request caching and reuse of independent features after the first change are separate work. [Exact equivalence and CPU measurements](../examples/ai-cad/transaction-reuse/README.md) retain representative inputs/replies and baseline executable hashes.

## Counterbored through-holes

`{kind:"counterbore_holes",id,input,depth,bore_radius,holes}` uses the same named `holes` entries (`id,x,y,radius`) as through-holes. `input` references an earlier extrusion or cylinder; `depth` and `bore_radius` reference parameters shared by the group. The native validator requires positive through radii, a strictly larger recess radius, and recess depth strictly between zero and stock height. The larger disks must be strictly inside stock and strictly separated. One group consumes the stock; kind changes still require explicit removal/recreation.

Evaluated analytic geometry retains each small through circle and adds `counterbore:{radius,depth}` in exact mm values. It has two inward cylindrical walls per hole and an upward annular shoulder at `height-depth`; `hole_depth` is absent. Removed volume per hole is `pi*(r²*h+(R²-r²)*d)`. Moment integration subtracts the through cylinder and only the additional upper annulus. Existing placement, linked instances, symbolic measurements and native history apply. This remains a bounded analytic family, with no general curved intersection fallback.

Display/STL meshes have separate lower/upper hole rings and explicit shoulder triangles. STEP translates these native surfaces without a solid Boolean; its float adapter requires shoulder width and remaining depth above 1e-6 mm. [Counterbore evidence](../examples/ai-cad/counterbores/README.md) includes actual browser/MCP recordings, closed exported meshes, independent solid comparisons and shoulder/aperture classification.

## Shared surface topology

Engine `--topology` accepts `{model,feature_id}`. Read-only HTTP `POST /api/topology` and MCP `cad_topology` accept `{expected_revision,feature_id}` for a terminal saved solid. The response includes revision (host only), feature ID, exact world-coordinate `vertices`, shared `edges`, `surfaces`, oriented `faces`, material `components`, closed `shells` and each `shell_euler`. It uses the same 4096-byte HTTP, 1 MiB engine request, 20-second subprocess and content/executable cache policies as measurements. Normal document and body responses are unchanged.

An edge has two vertex indices and a `curve`: `line`, or `quarter_circle` with exact center, signed coordinate axis and positive radius. Its stored direction spans positive 90 degrees around that axis. A face contains a surface reference and outer/inner loops of `{edge,forward}` uses. Planes use `normal·position=offset` with outward normal; cylinders use axis origin/direction, radius and `inward`. Cylinders have four rectangular patches with shared axial edges. Surface normals/offsets need not be normalized. Components partition faces; a cavity component contains multiple shells.

Analytic surface references use `feature/{source}/cap/top|bottom`, `feature/{source}/outer/cylinder`, `feature/{source}/outer/side/{sorted_vertex_ids}`, and `feature/{hole_group}/hole/{hole_id}/wall|floor|lower|upper|shoulder`. Source provenance is retained through rigid placement and linked copies. References must be paired with the selected body and revision: copies intentionally share source names. `naming:authored_surfaces` survives dimension changes and profile winding reversal while the authored role exists; renaming/removing a hole removes its old reference. Planar evaluated boundaries use `naming:revision_only` and `evaluated/face/{index}`. Vertex/edge indices and cylinder patches are always revision scoped. This is read-only inspection, not a face-edit command or a general persistent topology solution.

The exact native audit checks unique vertices, valid line/quarter-circle supports, surface membership, face-loop closure/orientation, two opposite face uses per edge, cyclic connected vertex links, shell Euler characteristic and component coverage. Analytic genus must match the number of through apertures. Plane-loop orientation integrates rational-plus-pi vector area; exact alternating-series bounds using `pi=16 atan(1/5)-4 atan(1/239)` certify its sign, refining at 32/128/512 terms and rejecting if unresolved. No floating-point pi predicate decides native validity. Counts are bounded to 1024 vertices, 2048 edges and 1024 faces/surfaces; computed rational components to 8192 bits.

This audit consumes internally generated, already validated models. It does not certify arbitrary imported surfaces, global self-intersections or shell nesting. The browser's **Inspect surfaces** shows authored roles and exact supports; inspection clears on selection/revision/preview changes, and stale asynchronous replies are discarded. [Retained native boundaries and independent STEP reconstruction](../examples/ai-cad/shared-topology/README.md) cover planar and analytic families. `topology_step.py` is a verification adapter only; it constructs/sews supplied surfaces and bounded cylindrical patches without native modeling Booleans. Its 1e-7 mm float tolerance does not alter native geometry or extend normal product export support.

## Shared surface context

`POST /api/selection` additionally accepts `{action:"select_surface",expected_revision,feature_id,surface_id}`; MCP `cad_select_surface` takes the same fields without `action`. The caller obtains `surface_id` from the selected body's `cad_topology` surface keys. The host validates terminal body, saved revision and exact surface membership under the document lock before atomically writing workspace context. Unsupported or missing references reject without modifying the previous selection. This selects an entire analytic surface (all four cylinder patches), not one tessellation triangle.

A surface selection uses version 2 of the disposable sidecar, storing only body/reference plus revision/content fingerprint. Version 1 body selections remain supported. Native documents, history and exports exclude this file. `cad_context` and HTTP context return optional `selected_surface:{reference,naming,support,faces,source_feature}` for surface selections; it is null when stale. `support` is the exact world-space surface record including `owner_feature`; `source_feature` is its authored feature definition from the validated model. Use `cad_explain` on the owner to identify shared drivers and other affected bodies before proposing typed feature/parameter edits. Owner provenance is not a promise that a single parameter changes only this surface.

Any model edit, undo or content replacement invalidates surface context, including changes that retain the authored name. Reselection must explicitly supply the new saved revision. A missing name never falls back to a nearby surface. Linked bodies intentionally share source names but have independent selected body IDs/world supports. Selecting a body clears surface detail; clearing selection clears both. This context conveys what is selected, not permission or an instruction to alter it. The existing revision-checked preview/commit protocol remains unchanged.

The browser adds **Select surface** inside each inspected surface's details, confirms the shared reference/source, and clears stale context on preview/save. Viewport highlighting remains whole-body; this adds list-based surface selection, not ray-picked surface highlighting. [Actual browser/MCP handoff and replay artifacts](../examples/ai-cad/surface-context/README.md) cover shared copy parameters, stale/missing references and unchanged native bytes during inspection/selection.

## Selection-bound edit preconditions

`preview` and `commit` accept optional `selection_guard:{feature_id,surface_id}`. Both keys are required when the guard is present; `surface_id:null` requires a body-only selection, while a string requires that exact surface. MCP preview/commit expose the same typed optional argument. Unguarded commands retain their existing contract. The guard is independent of model operations and must be copied unchanged from preview to save.

Under the document writer lock, after checking the expected revision, the host requires a current selection with matching body/surface, revision and full native-state fingerprint. The body must still be terminal and an optional surface must still exist in its exact topology. Missing/changed/cleared/stale context returns `selection_conflict`; malformed guards return `invalid_command`, and damaged sidecars retain `invalid_selection`. Failures do not write the document or consume a transaction ID. Do not remove the guard to bypass a conflict; inspect current context and replan or explicitly reselect the intended target.

Preview jobs check the guard under the same lock when capturing their immutable snapshot. Later selection changes do not cancel or rewrite an already running preview; saving rechecks the guard. A preview is not a reservation. Successful transaction receipt replay happens before current revision/selection checks, so an identical retry returns the original committed receipt without applying an edit twice, even after selection changes. The request digest includes the guard; reusing a transaction ID with a different guard rejects as `transaction_conflict`.

The browser automatically retains a selected surface guard in dimension/feature previews and their save commands. It keeps the unsaved preview visible if saving conflicts. The guard checks context identity at evaluation/save time; it is not an authorization boundary, geometric edit-locality proof, or a selection-generation counter. Changing away and explicitly returning to the identical selection at the same unchanged document permits the original proposal. [Interleaved browser/MCP evidence](../examples/ai-cad/selection-guard/README.md) verifies conflict, unchanged native bytes, explicit reselection and save.

## Viewport surface picking

The native `--mesh` request optionally accepts `include_surfaces:true`. It adds `triangle_surfaces`, one native surface-reference string per triangle. Default mesh/STL output is unchanged. Native mesh construction tags the generating cap, wall, floor or shoulder directly and resolves those roles through the same topology builder; it does not classify floating triangle positions to guess provenance. Placement preserves references. The display host requests these tags and includes the flag in its bounded cache key. Simple convex boundaries rendered directly in the browser use their revision-only native face index.

The browser groups disposable triangles by surface for drawing, preserving the underlying mesh. Its CPU hit test uses the same rebased Float32 positions and projection as the GPU, returns the frontmost displayed triangle's body/surface, then asks the host to validate that saved reference before sharing it. Unsupported/stale references reject. Picks during previews remain local body context. The feature-list Select solid action still chooses a whole body. Surface selection from either inspection or viewport highlights only that surface's triangle ranges after validation; lines retain their ordinary color. No geometry buffer is uploaded just to change selection or orbit.

Picking follows the disposable chord approximation and screen-space tolerances, not an exact native ray/surface intersection. Very small/thin geometry may remain valid natively while being unrenderable or unpickable. Coplanar/overlapping hits retain stable display-order tie breaking. All current body/revision naming and guarded-edit rules apply. [Actual cap/wall/shoulder picks and GPU draw evidence](../examples/ai-cad/surface-picking/README.md) retain the tagged mesh and exact shared context.
