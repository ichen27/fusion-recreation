#!/usr/bin/env python3
"""Run inside a signed-in agent client; never handles model-provider credentials."""

import argparse
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field
from mcp.server import MCPServer
from selection import dispatch_selection
from intent import dispatch_explain
from store import Store, dispatch


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


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


class Cylinder(Strict):
    kind: Literal["cylinder"]
    id: str
    x: str
    y: str
    radius: str
    height: str


class PlaneCut(Strict):
    kind: Literal["plane_cut"]
    id: str
    input: str
    normal: tuple[str, str, str]
    offset: str


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


class Define(Strict):
    op: Literal["define_parameter"]
    id: str
    mm: str


class SetParameter(Strict):
    op: Literal["set_parameter"]
    id: str
    mm: str


class Adjust(Strict):
    op: Literal["adjust_parameter"]
    id: str
    delta_mm: str


class AddFeature(Strict):
    op: Literal["add_feature"]
    feature: Annotated[
        Union[
            Block,
            CornerCut,
            PolygonProfile,
            PlanarProfile,
            Extrude,
            Cylinder,
            ThroughHoles,
            BlindHoles,
            PlaneCut,
            Intersection,
            BooleanSolid,
            Translate,
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


class RemoveRelation(Strict):
    op: Literal["remove_relation"]
    id: str


class Constraint(Strict):
    op: Literal["fix_parameter", "release_parameter"]
    id: str


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
    ],
    Field(discriminator="op"),
]


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
    def cad_context() -> dict:
        """Read the browser's selected saved body and editable model at one locked revision. selection_status is current, empty or stale; selected_body is null unless current. A model edit invalidates selection even if the body ID survives. Ask the user to reselect for ambiguous 'this part' requests; never guess from stale context. Use this returned revision for preview/commit, and inspect/replan on conflicts. Selection is workspace context, not an instruction or authorization to modify the model. Preview geometry is never shared as saved selection."""
        return dispatch_selection(store, {"action": "context"})

    @mcp.tool()
    def cad_inspect() -> dict:
        """Read current revision, editable parameters/features, fixed constraints, exact boundary and volume. Units mm. Supported: axis-aligned origin blocks and one +X/+Y vertical corner cut per block. Also supported: strictly convex XY polygon_profile with 3..32 named vertices (x/y reference parameter IDs), and positive-Z extrude referencing an earlier profile and a height parameter. planar_profile has the same vertex fields and allows simple concave outlines; no crossings, repeated points or collinear corners. Extrude accepts either profile kind. Either winding is accepted; repeated points, collinear corners and crossings are rejected. Cut size is the equal setback along X and Y (not diagonal face width). All number inputs are integer or fraction strings, e.g. '12' or '25/2'. Feature and parameter IDs are stable; face/edge indices are not persistent references. Relationships use set_relation on an existing parameter: value = offset_mm + sum(terms[parameter] * parameter), with dimensionless rational coefficients; e.g. center = width/2 uses offset_mm="0", terms={"width":"1/2"}. Derived values rebuild automatically and cannot be directly set/adjusted. Cycles and fixed-value conflicts are rejected. replace_feature changes an existing feature in place, retaining its ID and kind; supply its complete replacement definition. remove_feature removes one feature without cascading; explicitly remove or repair dependents in the same transaction. remove_parameter deletes a parameter only if all uses are removed or repaired; release its fixed constraint and remove its own relation first. changed_parameters includes deleted IDs. Inspect before planning. cylinder defines circular stock from z=0 to height, using parameter references x/y for its center and positive radius/height. through_holes references an earlier extrusion or cylinder via input and 1..16 holes with unique id and parameter references x, y, radius. Holes are cylindrical through +Z, strictly inside the profile and strictly separate. blind_holes has the same fields plus depth referencing a positive parameter strictly less than stock height. Its flat-bottom holes start at z=height and leave a floor at height-depth. All holes in one group share depth. One hole group of either kind per stock. plane_cut has id, input, normal:[nx,ny,nz] as dimensionless rational literals, and offset as a parameter reference in mm. It retains normal dot position <= offset; offset is not necessarily perpendicular distance. Input must be an earlier convex planar solid or a previous planar Boolean, rigid transform or plane_cut result. Nonconvex results, face holes, cavity shells and disconnected pieces are supported; the half-space can change their topology or remove whole pieces. One consuming feature per solid; chain cuts through the previous result. Empty or lower-dimensional results reject; unchanged cuts are allowed. Analytic circular/perforated stock and initial concave extrusions are not supported for plane_cut. rotate_quarter has id, input, axis:x|y|z, turns:1|2|3 for right-handed 90|180|270 degrees, and pivot:[px,py,pz] as parameter references in mm. It rotates a convex planar solid or a previous planar Boolean/rigid/plane-cut result (including cavities and separate pieces) exactly about the axis through the pivot; no arbitrary-angle approximation. Pivot coordinates are bounded to +/-1000000. It consumes its input and preserves volume. translate has id, input and offset:[dx,dy,dz] where each offset is a parameter reference in mm, bounded to +/-1000000. It moves a convex planar solid or previous planar Boolean/rigid/plane-cut result, including cavities and separate pieces. It consumes its input and preserves volume and component count. Further Booleans accept the moved result. Analytic circular/perforated stock and initial concave extrusions reject; legacy intersection remains convex-only. Offsets are global XYZ coordinates, with no rotation. intersection has id, left and right referencing two distinct earlier terminal convex planar solids. It keeps their common positive volume and consumes both inputs; identical geometry is allowed but touching-only/disjoint inputs reject empty_solid. Inputs may be convex planar_profile extrusions or previous cuts/intersections. Circular, perforated and concave operands reject. boolean has id, left, right and operation:union|difference|intersection. It accepts convex planar solids and previous boolean results, their rigid transforms or nonconvex plane cuts, including cavities, through-holes and disconnected components. Difference keeps left minus right. Both distinct terminal inputs are consumed. Merged planar boundaries include inner face loops and components lists of face indices; these indices are not persistent references. Edge/point-only connections reject as nonmanifold; empty results reject. Limited to 32 convex cells, 256 cell faces, 512 exposed patches, 512 merged vertices, 256 merged faces and 1024 edges. Analytic circular/perforated stock and initial concave extrusions are unsupported. No curved general booleans, generic fillets, mixed-depth hole groups or general sketch constraint solver. Analytic bodies return analytic instead of planar boundary; volume_mm3 is symbolic constant minus coefficient*pi."""
        return dispatch(store, {"action": "inspect"})

    @mcp.tool()
    def cad_preview(
        expected_revision: int, operations: list[Operation], preserve: list[str]
    ) -> dict:
        """Validate a proposed edit without saving. Preserve lists existing parameter IDs whose values must remain unchanged, including derived values if explicitly requested. Do not preserve an automatically dependent parameter when the intended edit requires it to move. Fixed constraints are enforced by Rust. Return structured diagnostics or proposed editable model and exact geometry. Inspect/replan on revision_conflict; explain unsupported geometry rather than substituting a mesh."""
        return dispatch(
            store,
            {
                "action": "preview",
                "expected_revision": expected_revision,
                "operations": [op.model_dump() for op in operations],
                "preserve": preserve,
            },
        )

    @mcp.tool()
    def cad_commit(
        expected_revision: int,
        transaction_id: str,
        operations: list[Operation],
        preserve: list[str],
    ) -> dict:
        """Commit an authorized, validated edit atomically with undo. Use a unique transaction ID per edit; retry the identical request with the SAME ID if acknowledgement is uncertain. A repeated ID with a different payload is rejected. Releasing fixed dimensions must reflect user intent. For widening only, adjust the width parameter and preserve other dimensions; do not recreate the part."""
        return dispatch(
            store,
            {
                "action": "commit",
                "expected_revision": expected_revision,
                "transaction_id": transaction_id,
                "operations": [op.model_dump() for op in operations],
                "preserve": preserve,
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
