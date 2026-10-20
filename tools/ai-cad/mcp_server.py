#!/usr/bin/env python3
"""Run inside a signed-in agent client; never handles model-provider credentials."""

import argparse
from typing import Annotated, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field
from mcp.server import MCPServer
from selection import dispatch_selection
from intent import dispatch_explain
from drawings import dispatch_drawing
from sections import dispatch_section
from measurements import dispatch_measure
from mass_properties import dispatch_mass_set
from materials import dispatch_material_mass
from inventory import dispatch_inventory
from topology import dispatch_topology
from edge_measurements import dispatch_edge_measure
from interference import dispatch_interference
from clearance import dispatch_clearance
from store import Store, dispatch


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SelectionGuard(Strict):
    feature_id: str
    surface_id: str | None


class Block(Strict):
    kind: Literal["block"]
    id: str
    width: str
    depth: str
    height: str


class CornerCut(Strict):
    kind: Literal["corner_cut"]
    id: str
    input: str
    size: str


class ProfileVertex(Strict):
    id: str
    x: str
    y: str


class PolygonProfile(Strict):
    kind: Literal["polygon_profile"]
    id: str
    vertices: list[ProfileVertex]


class PlanarProfile(PolygonProfile):
    kind: Literal["planar_profile"]


class Extrude(Strict):
    kind: Literal["extrude"]
    id: str
    profile: str
    height: str


class CoaxialBoolean(Strict):
    kind: Literal["coaxial_boolean"]
    id: str
    left: str
    right: str
    operation: Literal["union", "difference", "intersection"]


class CoaxialIntersection(Strict):
    kind: Literal["coaxial_intersection"]
    id: str
    left: str
    right: str


class StraightSweep(Strict):
    kind: Literal["straight_sweep"]
    id: str
    profile: str
    offset: tuple[str, str, str]


class Revolve(Strict):
    kind: Literal["revolve"]
    id: str
    profile: str


class PlanarLoft(Strict):
    kind: Literal["planar_loft"]
    id: str
    bottom: str
    top: str
    height: str


class Cylinder(Strict):
    kind: Literal["cylinder"]
    id: str
    x: str
    y: str
    radius: str
    height: str


class ConicalFrustum(Strict):
    kind: Literal["conical_frustum"]
    id: str
    x: str
    y: str
    bottom_radius: str
    top_radius: str
    height: str


class PlaneCut(Strict):
    kind: Literal["plane_cut"]
    id: str
    input: str
    normal: tuple[str, str, str]
    offset: str


class LinearPattern(Strict):
    kind: Literal["linear_pattern"]
    id: str
    input: str
    count: int = Field(strict=True, ge=1, le=16)
    step: tuple[str, str, str]


class MirrorPlane(Strict):
    kind: Literal["mirror_plane"]
    id: str
    input: str
    normal: tuple[str, str, str]
    offset: str
    keep_original: bool = Field(default=False, strict=True)


class PlanarShell(Strict):
    kind: Literal["planar_shell"]
    id: str
    input: str
    thickness: str
    opening_normal: tuple[str, str, str] | None = None


class RotateQuarter(Strict):
    kind: Literal["rotate_quarter"]
    id: str
    input: str
    axis: Literal["x", "y", "z"]
    turns: int = Field(strict=True, ge=1, le=3)
    pivot: tuple[str, str, str]


class Translate(Strict):
    kind: Literal["translate"]
    id: str
    input: str
    offset: tuple[str, str, str]


class Instance(Strict):
    kind: Literal["instance"]
    id: str
    source: str
    offset: tuple[str, str, str]


class Intersection(Strict):
    kind: Literal["intersection"]
    id: str
    left: str
    right: str


class BooleanSolid(Intersection):
    kind: Literal["boolean"]
    operation: Literal["union", "difference", "intersection"]


class Hole(Strict):
    id: str
    x: str
    y: str
    radius: str


class ThroughHoles(Strict):
    kind: Literal["through_holes"]
    id: str
    input: str
    holes: list[Hole]


class BlindHoles(ThroughHoles):
    kind: Literal["blind_holes"]
    depth: str
    depth_overrides: dict[str, str] | None = None


class CountersinkHoles(ThroughHoles):
    kind: Literal["countersink_holes"]
    depth: str
    rim_radius: str


class CounterboreHoles(ThroughHoles):
    kind: Literal["counterbore_holes"]
    depth: str
    bore_radius: str


class Define(Strict):
    op: Literal["define_parameter"]
    id: str
    mm: str = Field(
        description="Exact decimal, integer or fraction; optional mm, cm, m, in or ft suffix. Bare values are mm; saved values canonicalize to rational mm."
    )


class SetParameter(Strict):
    op: Literal["set_parameter"]
    id: str
    mm: str = Field(
        description="Exact decimal, integer or fraction; optional mm, cm, m, in or ft suffix. Bare values are mm; saved values canonicalize to rational mm."
    )


class Adjust(Strict):
    op: Literal["adjust_parameter"]
    id: str
    delta_mm: str = Field(
        description="Signed exact decimal, integer or fraction; optional mm, cm, m, in or ft suffix. Bare values are mm."
    )


class AddFeature(Strict):
    op: Literal["add_feature"]
    feature: Annotated[
        Union[
            Block,
            CornerCut,
            PolygonProfile,
            PlanarProfile,
            Extrude,
            PlanarLoft,
            Revolve,
            StraightSweep,
            CoaxialIntersection,
            CoaxialBoolean,
            Cylinder,
            ConicalFrustum,
            ThroughHoles,
            BlindHoles,
            CounterboreHoles,
            CountersinkHoles,
            PlaneCut,
            PlanarShell,
            MirrorPlane,
            LinearPattern,
            Intersection,
            BooleanSolid,
            Translate,
            Instance,
            RotateQuarter,
        ],
        Field(discriminator="kind"),
    ]


class ReplaceFeature(AddFeature):
    op: Literal["replace_feature"]
    id: str


class RemoveFeature(Strict):
    op: Literal["remove_feature"]
    id: str


class RemoveParameter(Strict):
    op: Literal["remove_parameter"]
    id: str


class Relation(Strict):
    offset_mm: str
    terms: dict[str, str]


class SetRelation(Strict):
    op: Literal["set_relation"]
    id: str
    relation: Relation


class LinearEquation(Strict):
    id: str
    terms: dict[str, str]
    offset_mm: str


class ConstrainLinear(Strict):
    op: Literal["constrain_linear"]
    targets: list[str]
    equations: list[LinearEquation]


class RemoveRelation(Strict):
    op: Literal["remove_relation"]
    id: str


class Constraint(Strict):
    op: Literal["fix_parameter", "release_parameter"]
    id: str


class Material(Strict):
    name: str
    density_kg_per_m3: str


class SetMaterial(Strict):
    op: Literal["set_material"]
    feature_id: str
    material: Material


class ClearMaterial(Strict):
    op: Literal["clear_material"]
    feature_id: str


Operation = Annotated[
    Union[
        Define,
        SetParameter,
        Adjust,
        AddFeature,
        ReplaceFeature,
        RemoveFeature,
        RemoveParameter,
        Constraint,
        SetRelation,
        RemoveRelation,
        ConstrainLinear,
        SetMaterial,
        ClearMaterial,
    ],
    Field(discriminator="op"),
]


class MassPart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feature_id: str
    density_kg_per_m3: str


def server(path):
    store = Store(path)
    mcp = MCPServer("Original CAD engine")

    @mcp.tool()
    def cad_explain(expected_revision: int, feature_id: str) -> dict:
        """Explain a selected or retained feature's source chain, controlling dimensions, fixed/derived status and potential edit impact. Returns exact values, affine relations, root driving parameters, affected parameters/features and terminal bodies across the whole model. Dependency reachability is conservative: it does not prove a numeric edit changes geometry or succeeds. Use preview to validate proposed edits and preserve intended dimensions. Fixed drivers still require explicit user intent before release. Read-only and revision-bound; inspect/replan on conflicts."""
        return dispatch_explain(
            store, {"expected_revision": expected_revision, "feature_id": feature_id}
        )

    @mcp.tool()
    def cad_inventory(expected_revision: int) -> dict:
        """Read every saved terminal solid as a separate inventory row: stable feature ID, feature kind, quantity1, direct linked-instance source, exact volume_mm3 and resolved persistent material/status. Returns source revision/model SHA256, material counts and CSV. No equal-volume/shape grouping or part-number equivalence is inferred. Consumed features and standalone profiles are excluded; a disconnected or patterned body is one row, not a count of connected components. Overlapping terminal bodies are listed separately. Unassigned/conflicting materials remain explicit; do not invent densities. This is a flat body inventory, not an assembly hierarchy or manufacturing BOM. Read-only; refresh on revision_conflict. CSV prefixes formula-like cells with an apostrophe; JSON retains exact strings. Import exact numeric CSV columns as text to avoid spreadsheet conversion."""
        return dispatch_inventory(store, dict(expected_revision=expected_revision))

    @mcp.tool()
    def cad_material_mass(expected_revision: int, feature_ids: list[str]) -> dict:
        """Read combined mass, center and inertia for1..16 distinct saved terminal solids using their persistent uniform materials. Inspect resolved_materials first. Missing or conflicting material ancestry rejects; do not invent a density. Set or replace a feature override through cad_preview/cad_commit with {op:'set_material',feature_id,material:{name,density_kg_per_m3}}. Positive rational density is kg/m³; name is1..80 non-control characters without outer whitespace. Unary edits and linked copies inherit; Boolean difference takes the left target's material. Other combinations require identical names and densities on every input or report conflict. An explicit output override resolves it as a uniform whole solid, not mixed internal regions. clear_material removes a direct override and restores inheritance; clear overrides explicitly before deleting their feature. Native geometry and explicit-density measurements are unchanged. Every selected occurrence counts separately, including overlap."""
        return dispatch_material_mass(
            store, dict(expected_revision=expected_revision, feature_ids=feature_ids)
        )

    @mcp.tool()
    def cad_section(
        expected_revision: int,
        feature_id: str,
        axis: Literal["X", "Y", "Z"],
        offset_mm: str,
    ) -> dict:
        """Read an exact coordinate-plane cross-section of one saved terminal planar solid. Axis X/Y/Z and integer/fraction offset_mm specify the world-coordinate cut plane. Returns exact planar loops, hole nesting, area in mm², 3D area centroid in mm, source revision/hash and a hatched SVG reference view. Only the selected solid participates. Curved solids reject; planes through any native vertex reject as section_degenerate, so choose a different exact offset. Empty cuts reject. This does not remove material or save a feature, drawing or annotation. Fit-to-page SVG must not be measured; no manufacturing tolerances or hidden geometry beyond the cut plane are included."""
        return dispatch_section(
            store,
            dict(
                expected_revision=expected_revision,
                feature_id=feature_id,
                axis=axis,
                offset_mm=offset_mm,
            ),
        )

    @mcp.tool()
    def cad_reference_sheet(
        expected_revision: int,
        feature_id: str,
        style: Literal["all_edges", "planar_hidden"] = "all_edges",
    ) -> dict:
        """Read a revision-bound SVG orthographic reference sheet for one saved terminal solid. Returns SVG text, exact XYZ bounds/extents in mm, source-model SHA-256 and top/front/right projection counts. Default all_edges shows all native edges, including occluded edges and smooth surface seams. Optional planar_hidden classifies exact visible/hidden segments for planar solids only and draws hidden segments dashed; curved solids reject this style. Occlusion uses the selected solid only. Circular edges remain SVG arcs where face-on, and project to lines edge-on. No curved hidden-line classification, section views, tolerances or manufacturing annotations; common fit-to-sheet scale must not be used to measure dimensions. Native model and history remain unchanged."""
        return dispatch_drawing(
            store,
            {
                "expected_revision": expected_revision,
                "feature_id": feature_id,
                "style": style,
            },
        )

    @mcp.tool()
    def cad_mass_properties(expected_revision: int, parts: list[MassPart]) -> dict:
        """Read additive mass, center of mass in mm and centroidal inertia in kg m² for 1..16 distinct terminal solids. Each part supplies feature_id and a positive rational density_kg_per_m3 string. Every selected occurrence is counted separately, including spatial overlaps; this does not Boolean-union material or detect collisions. Exact rational/pi expressions, global XYZ axes, read-only and revision-bound. Materials are not persisted. Use each occurrence once; source and linked copies are distinct occurrences. Includes per-part measurements and explicit overlap_policy."""
        return dispatch_mass_set(
            store,
            {
                "expected_revision": expected_revision,
                "parts": [part.model_dump() for part in parts],
            },
        )

    @mcp.tool()
    def cad_measure(
        expected_revision: int, feature_id: str, density_kg_per_m3: Optional[str] = None
    ) -> dict:
        """Read exact world-axis bounds, volume centroid and centroidal volume inertia tensor for a terminal supported solid. Values are exact arithmetic strings: rational numbers or rational functions of pi (using integers, parentheses, +, -, *, / and pi); units are mm, mm^3 and mm^5. The tensor integrates (r^2 I - r r^T) dV about the volume centroid in global XYZ axes. It assumes uniform density for interpreting the centroid as center of mass. Optional density_kg_per_m3 is a positive strict rational string in kg/m^3. It adds mass_properties with canonical density, exact mass_kg and centroidal_inertia_kg_m2 in global XYZ. Density is a read-only measurement input, not a saved material assignment or mixed-density assembly calculation. Omission retains geometric measurements only. Includes planar cavities/disconnected pieces as one selected body. Circular stock and through/blind/counterbored-hole groups, including exact placements, are supported with symbolic pi integration. Read-only and revision-bound; does not sum overlapping bodies or infer clearance/collision."""
        return dispatch_measure(
            store,
            {
                "expected_revision": expected_revision,
                "feature_id": feature_id,
                "density_kg_per_m3": density_kg_per_m3,
            },
        )

    @mcp.tool()
    def cad_clearance(expected_revision: int, left: str, right: str) -> dict:
        """Measure exact minimum material separation between distinct saved terminal planar bodies. Same supported planar stock, cuts, Booleans, cavities, disconnected pieces and placements as cad_interference; curved analytic stock rejects unsupported_clearance. relation is separated, touching or overlapping. distance_squared_mm2 is rational and distance_mm is rational or sqrt(rational); approximation is display-only. Separated/touching results provide one exact rational closest-point pair, ordered left/right; ties need not return the same pair after edits or reversed input order. Overlapping material has zero separation and null closest_points_mm: no penetration depth is measured. This is straight Euclidean material distance, including cavity walls, not an assembly fit/tolerance/motion guarantee. Read-only and revision-bound; refresh on stale references. Resource-limit errors never represent a partial clearance answer."""
        return dispatch_clearance(
            store,
            {"expected_revision": expected_revision, "left": left, "right": right},
        )

    @mcp.tool()
    def cad_interference(expected_revision: int, left: str, right: str) -> dict:
        """Check exact positive-volume overlap between two distinct terminal planar bodies at the saved revision. Supports unperforated polygon extrusions, planar lofts, cuts, Booleans, cavities, disconnected pieces and their supported placements/instances. overlap_volume_mm3 is exact rational; positive_volume_overlap indicates strictly positive shared material volume. Zero does NOT prove clearance or absence of face/edge/point contact. Curved/perforated analytic stock rejects unsupported_interference; never interpret rejection as no collision. This read-only check creates/consumes no features and changes no native history. Inspect/replan on stale revisions. No contact geometry, distance, motion or assembly-joint analysis is provided."""
        return dispatch_interference(
            store,
            {"expected_revision": expected_revision, "left": left, "right": right},
        )

    @mcp.tool()
    def cad_measure_edge(
        expected_revision: int,
        feature_id: str,
        edge_index: Annotated[int, Field(strict=True, ge=0)],
    ) -> dict:
        """Measure one shared edge from cad_topology at the same saved body/revision. edge_index is zero-based and must be refreshed after edits. length_mm is an exact rational, sqrt(rational), or rational*pi expression; length_approx_mm is for display only. Quarter-circle length follows the arc; chord_mm and chord_squared_mm2 describe straight endpoint separation. Returns exact endpoints/support and incident surface IDs. patch_seam:true means a subdivision within one smooth surface, not a physical sharp edge. Read-only; stale revisions or missing edges reject without retargeting. This does not measure distance between arbitrary entities."""
        return dispatch_edge_measure(
            store,
            {
                "expected_revision": expected_revision,
                "feature_id": feature_id,
                "edge_index": edge_index,
            },
        )

    @mcp.tool()
    def cad_topology(expected_revision: int, feature_id: str) -> dict:
        """Inspect exact world-space surfaces and shared vertices/edges/face loops for one terminal solid at the saved revision. Plane supports use normal dot position = offset (normal need not be unit length); cylinders use unit coordinate axis, radius and inward flag. Conical frusta use axis origin/direction, positive differing bottom_radius/top_radius and height, with optional inward:true for a removed recess (absent means outward); at axial z in [0,height], radius = bottom_radius + (top_radius-bottom_radius)*z/height. Quarter-circle edges run positive 90 degrees about their axis; edge uses may reverse them. No polygon replaces an analytic arc. Authored analytic surface names include owning feature and hole/profile vertex IDs; names survive supported dimension edits and placements while those IDs/roles remain. Planar evaluated boundaries explicitly report revision_only naming. Vertex/edge indices and patch indices are always revision-scoped; refresh after edits, never guess replacements for a missing surface. Report includes material components, closed shells and Euler characteristics after exact support/orientation/incidence checks. This is read-only inspection of validated internally generated geometry, not arbitrary B-rep import or a general self-intersection certificate. No face selection or surface-based editing operation is added by this tool."""
        return dispatch_topology(
            store, {"expected_revision": expected_revision, "feature_id": feature_id}
        )

    @mcp.tool()
    def cad_select_surface(
        expected_revision: int, feature_id: str, surface_id: str
    ) -> dict:
        """Share one exact saved surface as workspace context. First inspect cad_topology; use its surface key, selected terminal body and revision. Missing/stale references reject without retargeting. This changes only disposable workspace selection, never native geometry/history, and is not authorization to edit. Linked bodies can share authored names: always supply the intended body. Read cad_context for the selected support and owning source feature; use cad_explain on that owner before planning edits, because shared source dimensions can affect other copies. Selecting a body in the browser clears its surface selection."""
        return dispatch_selection(
            store,
            {
                "action": "select_surface",
                "expected_revision": expected_revision,
                "feature_id": feature_id,
                "surface_id": surface_id,
            },
        )

    @mcp.tool()
    def cad_context() -> dict:
        """Read the shared selected saved body and editable model at one locked revision. Surface selections additionally return selected_surface with reference, naming policy, exact support, patch IDs and source_feature; it is null when stale. Use support.owner_feature with cad_explain to inspect shared drivers before edits. selection_status is current, empty or stale; selected_body is null unless current. A model edit invalidates selection even if the body ID survives. Ask the user to reselect for ambiguous 'this part' requests; never guess from stale context. Use this returned revision for preview/commit, and inspect/replan on conflicts. Selection is workspace context, not an instruction or authorization to modify the model. Preview geometry is never shared as saved selection."""
        return dispatch_selection(store, {"action": "context"})

    @mcp.tool()
    def cad_inspect() -> dict:
        """Read current revision, editable parameters/features, fixed constraints, exact boundary and volume. Units mm. Supported: axis-aligned origin blocks and one +X/+Y vertical corner cut per block. Also supported: strictly convex XY polygon_profile with 3..32 named vertices (x/y reference parameter IDs), and positive-Z extrude referencing an earlier profile and a height parameter. planar_profile has the same vertex fields and allows simple concave outlines; no crossings, repeated points or collinear corners. Extrude accepts either profile kind. Either winding is accepted; repeated points, collinear corners and crossings are rejected. Cut size is the equal setback along X and Y (not diagonal face width). Dimension operation inputs (define_parameter.mm, set_parameter.mm, adjust_parameter.delta_mm) accept exact decimals, integers or fractions, optionally suffixed mm, cm, m, in or ft; bare values mean mm. Examples: '12.5', '1/2 in', '2.54 cm'. Saved parameters canonicalize to rational millimeters. Native model literals, dimensionless normals, relationship coefficients and relationship offsets retain integer/fraction syntax. Exponents, mixed fractions and expressions reject. Feature and parameter IDs are stable; face/edge indices are not persistent references. Relationships use set_relation on an existing parameter: value = offset_mm + sum(terms[parameter] * parameter), with dimensionless rational coefficients; e.g. center = width/2 uses offset_mm="0", terms={"width":"1/2"}. Derived values rebuild automatically and cannot be directly set/adjusted. Cycles and fixed-value conflicts are rejected. replace_feature changes an existing feature in place, retaining its ID and kind; supply its complete replacement definition. remove_feature removes one feature without cascading; explicitly remove or repair dependents in the same transaction. remove_parameter deletes a parameter only if all uses are removed or repaired; release its fixed constraint and remove its own relation first. changed_parameters includes deleted IDs. constrain_linear takes targets (1..16 existing parameter IDs) and equations (1..32 {id,terms,offset_mm} rows), meaning sum(terms[parameter]*parameter)=offset_mm. Coefficients and offsets use strict rational strings; each row has at most8 nonzero terms. Exact symbolic elimination replaces target relationships with equivalent affine formulas, retained in model.relations. Non-target parameters remain drivers, including later edits. Original row labels and redundant equations are not persisted. Underdetermined targets, contradictory equations, constraints on non-target drivers, relation cycles and arithmetic overflow reject atomically. Include dependent dimensions among targets; do not silently fix free drivers or guess a solution. Each solved formula retains at most8 input terms and128-bit exact arithmetic limits. Existing fixed/preserve rules still apply. This solves linear equalities only, not distances, angles, inequalities or general nonlinear sketch constraints. Inspect before planning. coaxial_boolean has id,left,right,operation (union/difference/intersection) and consumes two terminal coaxial analytic solids. It accepts convex or simple concave radial sections of cylinders, frusta, revolutions and earlier coaxial results. The exact result must have one connected radial region without interior contour holes; axis contact needs one connected flat-ended axis edge. Disconnected regions, enclosed radial holes or multiple axis contacts reject with unsupported_coaxial_result; empty material rejects. Original exact segment splitting and material-side classification construct the radial section, with bounded coordinates/segment counts and no external modeling fallback. Generated surfaces remain revision-only. Inspect before planning. coaxial_intersection has id,left,right and consumes two distinct terminal analytic solids. Cylinders, frusta and revolutions with simple convex or concave radius/axial polygon sections are supported, including stepped shafts, undercuts, hollow rings and previous coaxial results. They must share exactly the same coordinate-axis line; translations, quarter-turn placements and opposite axis directions are normalized exactly. Offset/crossing axes and perforated stock reject. Results need one connected radial contour without enclosed holes; unsupported_coaxial_result diagnoses separate regions, cavities or unsupported axis contact. The exact common section produces analytic boundary/moments; touching without positive common volume rejects. Generated surfaces are revision-only references. This is not a general curved Boolean operation. Inspect before planning. straight_sweep has id, profile and offset:[x_parameter,y_parameter,z_parameter]. It translates an earlier simple polygon_profile/planar_profile in XY along an exact XYZ displacement, retaining its orientation and editable source. Z displacement must be nonzero (either sign); zero produces no solid volume. Displacement components and resulting coordinates must remain within +/-1000000 mm. Concave sketches are supported within existing planar-cell budgets. The result supports planar cuts/Booleans, placements, exact moments and exports. No curved path, twist or changing cross-section. Sweep face/edge indices are evaluated references, not persistent authored surface identities. Inspect before planning. revolve has id and profile referencing an earlier polygon_profile or planar_profile. It turns the entire profile 360 degrees about global Z: sketch X becomes radius and sketch Y becomes axial Z. The original sketch remains editable. Radii must be nonnegative; the outline must be simple. Axis contact is allowed only through exactly two adjacent zero-radius vertices joined along the axis, with horizontal radial segments at both ends (flat caps); isolated apexes, pinches or multiple axis contacts reject. Strictly positive-radius outlines create hollow rings, including conical inner/outer walls and concave stepped sections. No partial turn, curved sketch edge or curved Boolean is supported. Exact volume/moments, shared analytic topology, placements/linked copies and native/STL/STEP exports are supported. mirror_plane has id,input,normal:[nx,ny,nz],offset and optional keep_original (default false). It exactly reflects planar material across normal dot position = offset, where normal values are dimensionless rational literals and offset references a mm parameter. Scale normal and offset together to preserve the same plane. Normal must be nonzero. keep_original=true retains the earlier source and creates a separately selectable linked reflected body; false consumes a terminal input. Source dimensions and offset relations remain editable. Convex, concave, cavity and disconnected planar material is supported; analytic curved stock rejects. Geometry remains rational even for oblique planes; reflection reverses boundary orientation internally to preserve outward faces and positive volume. Existing exact-coordinate and geometry budgets apply. linear_pattern has id,input,count,step:[dx,dy,dz]. It consumes terminal planar material and unions count copies, including the original, at integer multiples of the parameter-backed global step. Count is an integer literal 1..16; replace_feature edits count. Source dimensions and affine step relations remain linked. Overlapping copies merge, face-touching copies join, and disconnected components remain in one pattern body. This is material repetition, not independent assembly instances. Nonmanifold edge/point joins reject. Curved stock is unsupported. For count>1 the step must be nonzero; each step component and total displacement must be within +/-1000000 mm. Existing planar cell/face budgets may reject complex patterns below the count limit. planar_shell has id,input,thickness and optional opening_normal:[nx,ny,nz] as dimensionless rational literals. It consumes an earlier terminal convex planar solid and offsets retained faces inward by a positive parameter-backed perpendicular thickness. Omit opening_normal for a closed cavity; otherwise its outward direction must match exactly one face, which opens. Direction scale is irrelevant. Curved/nonconvex inputs reject; if any retained face needs an irrational uniform offset, unsupported_shell rejects rather than approximating. Thickness must leave positive interior volume. Source features remain editable, and the planar result supports later Booleans/cuts, placement, measurements, interference/clearance and exports. Opening matches direction rather than a persistent face index; inspect/preview after upstream changes. planar_loft has id, bottom, top and height: bottom/top reference earlier strictly convex polygon_profile or planar_profile sketches. Matching vertex IDs connect the bottom at z=0 to the top at positive height. Both profiles must have the same vertex IDs and edge adjacency; every corresponding side must be exactly planar and the whole solid convex, otherwise unsupported_loft. Profiles are retained; no input solids are consumed. Equal sections allow a straight or skewed prism. Arbitrary twisted/curved lofts are unsupported. The planar result supports cuts, Booleans, placement, measurements and exports; hole groups cannot directly use it. conical_frustum defines tapered round stock with parameter references x, y, bottom_radius, top_radius and height. Both radii and height must be positive, and radii must differ; equal radii use cylinder. It has two circular caps and an exact conical wall; no apex, holes, plane cuts or Booleans on this stock. Exact movement, quarter turns, linked copies, symbolic moments, surface inspection and exports are supported. cylinder defines circular stock from z=0 to height, using parameter references x/y for its center and positive radius/height. through_holes references an earlier extrusion or cylinder via input and 1..16 holes with unique id and parameter references x, y, radius. Holes are cylindrical through +Z, strictly inside the profile and strictly separate. blind_holes has the same fields plus depth referencing a positive parameter strictly less than stock height. Its flat-bottom holes start at z=height and leave a floor at height-depth. Optional depth_overrides maps hole IDs in this group to individual depth parameter IDs; omitted holes use depth. Every depth must be positive and strictly below height. Removing a hole must also remove its override. counterbore_holes has the through_holes fields plus depth and bore_radius as parameter references. Each hole keeps its own through radius; the shared upper recess radius must be larger than every through radius and the shared depth must be strictly below stock height. Recess disks must stay strictly inside stock and apart. All cylinder walls and annular shoulders remain analytic. countersink_holes has the through_holes fields plus depth and rim_radius parameter references: a conical recess expands from each through radius at height-depth to a larger shared rim radius at the top. Positive depth must be strictly below stock height, and top disks must be strictly inside stock and separate. Recess angle is determined by radii/depth, not an angle parameter. Inward conical surfaces and exact symbolic moments remain editable. One hole group per stock. plane_cut has id, input, normal:[nx,ny,nz] as dimensionless rational literals, and offset as a parameter reference in mm. It retains normal dot position <= offset; offset is not necessarily perpendicular distance. Input must be an earlier convex planar solid, unperforated simple-profile extrusion (including concave outlines), or a previous planar Boolean, rigid transform or plane_cut result. Nonconvex results, face holes, cavity shells and disconnected pieces are supported; the half-space can change their topology or remove whole pieces. One consuming feature per solid; chain cuts through the previous result. Empty or lower-dimensional results reject; unchanged cuts are allowed. Analytic circular/perforated stock is not supported for plane_cut. rotate_quarter has id, input, axis:x|y|z, turns:1|2|3 for right-handed 90|180|270 degrees, and pivot:[px,py,pz] as parameter references in mm. It rotates any currently supported planar or analytic solid, including circular stock, through/blind-hole groups, cavities and separate pieces. Exact circles/cylinders retain local analytic geometry with placement axes/origin; no arbitrary-angle approximation. Pivot coordinates are bounded to +/-1000000. It consumes its input and preserves volume. translate has id, input and offset:[dx,dy,dz] where each offset is a parameter reference in mm, bounded to +/-1000000. It moves any supported solid, consumes its input and preserves exact volume. instance has id, source and offset:[dx,dy,dz] with the same input/range limits as translate. It creates a linked translated copy without consuming the earlier source; source dimensions propagate to all copies, while offsets place each independently. A source can be an earlier consumed historical solid or another instance; forward/self references reject. Analytic results include optional placement with signed-permutation axes rows and rational origin: world = axes*local + origin. Native circles and cylindrical walls remain analytic; display/STL tessellation is disposable. Analytic placements cannot feed planar Booleans or plane cuts; add/edit hole groups on their original stock before placement. Legacy intersection remains convex-only. This is linked placement, not assembly joints or collision checking. Distinct bodies may overlap and their volumes are not a union total. intersection has id, left and right referencing two distinct earlier terminal convex planar solids. It keeps their common positive volume and consumes both inputs; identical geometry is allowed but touching-only/disjoint inputs reject empty_solid. Inputs may be convex planar_profile extrusions or previous cuts/intersections. Circular, perforated and concave operands reject. boolean has id, left, right and operation:union|difference|intersection. It accepts convex planar solids, unperforated simple-profile extrusions including concave outlines, and previous boolean results, their rigid transforms or nonconvex plane cuts, including cavities, through-holes and disconnected components. Difference keeps left minus right. Both distinct terminal inputs are consumed. Merged planar boundaries include inner face loops and components lists of face indices; these indices are not persistent references. Edge/point-only connections reject as nonmanifold; empty results reject. Limited to 32 convex cells, 256 cell faces, 512 exposed patches, 512 merged vertices, 256 merged faces and 1024 edges. Analytic circular/perforated stock is unsupported. Simple concave profiles are decomposed using exact rational predicates; no float mesh defines native geometry. No curved general booleans, generic fillets or general sketch constraint solver. Analytic bodies return analytic instead of planar boundary; volume_mm3 is symbolic constant minus coefficient*pi."""
        return dispatch(store, {"action": "inspect"})

    @mcp.tool()
    def cad_preview(
        expected_revision: int,
        operations: list[Operation],
        preserve: list[str],
        selection_guard: SelectionGuard | None = None,
    ) -> dict:
        """Validate a proposed edit without saving. For an edit based on shared selection, pass selection_guard={feature_id,surface_id}, using null surface_id only for body-only selection. Copy the same guard to commit. Selection conflicts require reading current context and replanning; never silently drop the guard. Preserve lists existing parameter IDs whose values must remain unchanged, including derived values if explicitly requested. Do not preserve an automatically dependent parameter when the intended edit requires it to move. Fixed constraints are enforced by Rust. Return structured diagnostics or proposed editable model and exact geometry. Inspect/replan on revision_conflict; explain unsupported geometry rather than substituting a mesh."""
        return dispatch(
            store,
            {
                "action": "preview",
                "expected_revision": expected_revision,
                "operations": [op.model_dump(exclude_none=True) for op in operations],
                "preserve": preserve,
                **(
                    {"selection_guard": selection_guard.model_dump()}
                    if selection_guard is not None
                    else {}
                ),
            },
        )

    @mcp.tool()
    def cad_commit(
        expected_revision: int,
        transaction_id: str,
        operations: list[Operation],
        preserve: list[str],
        selection_guard: SelectionGuard | None = None,
    ) -> dict:
        """Commit an authorized, validated edit atomically with undo. Retain the preview's selection_guard when the edit depends on shared selection. It requires the same current body/surface and document fingerprint under the writer lock. A selection_conflict must be resolved by inspecting and replanning, never by removing the guard. This checks context identity, not whether operations affect only the selected surface; inspect source impact and preserve intended dimensions. Use a unique transaction ID per edit; retry the identical request with the SAME ID if acknowledgement is uncertain. A repeated ID with a different payload is rejected. Releasing fixed dimensions must reflect user intent. For widening only, adjust the width parameter and preserve other dimensions; do not recreate the part."""
        return dispatch(
            store,
            {
                "action": "commit",
                "expected_revision": expected_revision,
                "transaction_id": transaction_id,
                "operations": [op.model_dump(exclude_none=True) for op in operations],
                "preserve": preserve,
                **(
                    {"selection_guard": selection_guard.model_dump()}
                    if selection_guard is not None
                    else {}
                ),
            },
        )

    @mcp.tool()
    def cad_history(
        action: Literal["undo", "redo"], expected_revision: int, transaction_id: str
    ) -> dict:
        """Undo or redo one complete edit; revision increases monotonically. Uses the same document as the browser and other clients."""
        return dispatch(
            store,
            {
                "action": action,
                "expected_revision": expected_revision,
                "transaction_id": transaction_id,
            },
        )

    return mcp


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True)
    args = parser.parse_args()
    server(args.store).run()
