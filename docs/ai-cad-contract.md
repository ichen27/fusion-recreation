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

`{kind:"blind_holes",id,input,depth,holes}` has the same stock and named circle references as `through_holes`, plus a depth parameter. Require `0 < depth < stock height` exactly. Holes descend from the top face and end at `height − depth`; all holes in the group share this depth. One group of either kind consumes a stock feature. Switching kind requires explicit removal/recreation because `replace_feature` preserves kind.

The existing analytic prism representation gains optional `hole_depth`. Its absence retains full-depth through-hole behavior. With depth present, the bottom stock face is unperforated, each inner cylinder spans `height-depth` to `height`, and each circular floor has an upward material normal. Removed volume is `π × sum(radius²) × depth`. Circle containment/separation rules and IDs are unchanged. Old serialized replies remain unchanged.

Display/STL construct separate outer bottom and pocket floor faces. Numerically collapsed depth or floor rejects tessellation without invalidating the exact model. STEP explicitly translates these faces and walls; both depth and remaining floor must exceed 1e−6 mm. [Independent surface, floor-containment, volume and browser evidence](../examples/ai-cad/blind-holes/README.md). This does not provide drill-tip cones, counterbores, mixed-depth groups, intersecting pockets, arbitrary axes or features on already perforated stock.

## Convex arbitrary-plane cuts

`{kind:"plane_cut",id,input,normal:[nx,ny,nz],offset}` retains `nx*x + ny*y + nz*z <= parameter(offset)`. Normal components are dimensionless rational literals, not parameter references, and must not all be zero. Offset references an existing mm parameter and is not necessarily perpendicular distance. The input must be an earlier body with a convex planar boundary: block, strict convex profile extrusion, corner cut or prior plane cut. Analytic/circular/perforated and simple-planar-profile representations reject explicitly. Each input can have one consuming feature; subsequent cuts reference the preceding cut.

Cuts retain the existing planar `boundary` representation, exact rational vertices and volume. Empty or lower-dimensional results return `empty_solid`; unchanged cuts remain valid features. Parameters, previews, transactions, undo and feature replacement retain existing semantics. Generated face/edge indices are not persistent references. The original boundary kernel enforces its existing 128-vertex/128-face/384-edge and 1024-bit component bounds. [Browser and independent STEP/STL acceptance evidence](../examples/ai-cad/plane-cuts/README.md).

## Multi-body STL archives

The loopback viewer's read-only `GET /api/export.zip?revision=N&segments=S` exports every terminal solid from one validated saved snapshot. A later concurrent edit cannot mix revisions among its files. Single-body `/api/export.stl` remains supported. The ZIP contains numerically prefixed STL filenames and `manifest.json` with revision, mm units, circle segment count, feature/file mapping, exact source volumes, triangle counts and maximum radial chord error. Prefixes avoid case-folded filename collisions. No native history is embedded. Empty documents, stale revisions, failed tessellation or more than 64 MiB of uncompressed STL reject the entire archive. The browser uses one ZIP download when multiple solids are saved.

## Native file workflow

`GET /api/export.cad?revision=N` returns a locked, validated native snapshot with complete history and receipts; a stale revision rejects. `preview_import` and `import` accept this envelope as `document`. Both validate every source history model and checksum. Import retains the destination revision/receipts, adds its prior model to undo and clears redo. Source history/receipts are not copied. Existing fixed/relationship constraints belong to the imported model; replacement is explicit rather than a constrained dimension edit. The browser labels this action **Replace model**. Reopen a downloaded file as the host store to retain that file’s full history. [Recorded acceptance and portable artifacts](../examples/ai-cad/native-project/README.md). These commands are available through the document host/HTTP API; no new MCP import tool is exposed.
