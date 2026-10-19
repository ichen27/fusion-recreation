#!/usr/bin/env python3
"""Run inside a signed-in agent client; never handles model-provider credentials."""

import argparse
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field
from mcp.server import MCPServer
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
    def cad_inspect() -> dict:
        """Read current revision, editable parameters/features, fixed constraints, exact boundary and volume. Units mm. Supported: axis-aligned origin blocks and one +X/+Y vertical corner cut per block. Also supported: strictly convex XY polygon_profile with 3..32 named vertices (x/y reference parameter IDs), and positive-Z extrude referencing an earlier profile and a height parameter. planar_profile has the same vertex fields and allows simple concave outlines; no crossings, repeated points or collinear corners. Extrude accepts either profile kind. Either winding is accepted; repeated points, collinear corners and crossings are rejected. Cut size is the equal setback along X and Y (not diagonal face width). All number inputs are integer or fraction strings, e.g. '12' or '25/2'. Feature and parameter IDs are stable; face/edge indices are not persistent references. Relationships use set_relation on an existing parameter: value = offset_mm + sum(terms[parameter] * parameter), with dimensionless rational coefficients; e.g. center = width/2 uses offset_mm="0", terms={"width":"1/2"}. Derived values rebuild automatically and cannot be directly set/adjusted. Cycles and fixed-value conflicts are rejected. replace_feature changes an existing feature in place, retaining its ID and kind; supply its complete replacement definition. remove_feature removes one feature without cascading; explicitly remove or repair dependents in the same transaction. remove_parameter deletes a parameter only if all uses are removed or repaired; release its fixed constraint and remove its own relation first. changed_parameters includes deleted IDs. Inspect before planning. cylinder defines circular stock from z=0 to height, using parameter references x/y for its center and positive radius/height. through_holes references an earlier extrusion or cylinder via input and 1..16 holes with unique id and parameter references x, y, radius. Holes are cylindrical through +Z, strictly inside the profile and strictly separate. blind_holes has the same fields plus depth referencing a positive parameter strictly less than stock height. Its flat-bottom holes start at z=height and leave a floor at height-depth. All holes in one group share depth. One hole group of either kind per stock. plane_cut has id, input, normal:[nx,ny,nz] as dimensionless rational literals, and offset as a parameter reference in mm. It retains normal dot position <= offset; offset is not necessarily perpendicular distance. Input must be an earlier convex planar solid, including a previous plane_cut. One consuming feature per solid; chain cuts through the previous result. Empty or lower-dimensional results reject; unchanged cuts are allowed. Circular/perforated/concave inputs are not supported for plane_cut. No tangency between holes, breakout, mixed-depth groups, generic fillets, sketch constraint solving or general booleans. Analytic bodies return analytic instead of planar boundary; volume_mm3 is symbolic constant minus coefficient*pi."""
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
