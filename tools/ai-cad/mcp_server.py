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


class Extrude(Strict):
    kind: Literal["extrude"]
    id: str
    profile: str
    height: str


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
        Union[Block, CornerCut, PolygonProfile, Extrude], Field(discriminator="kind")
    ]


class Constraint(Strict):
    op: Literal["fix_parameter", "release_parameter"]
    id: str


Operation = Annotated[
    Union[Define, SetParameter, Adjust, AddFeature, Constraint],
    Field(discriminator="op"),
]


def server(path):
    store = Store(path)
    mcp = MCPServer("Original CAD engine")

    @mcp.tool()
    def cad_inspect() -> dict:
        """Read current revision, editable parameters/features, fixed constraints, exact boundary and volume. Units mm. Supported: axis-aligned origin blocks and one +X/+Y vertical corner cut per block. Also supported: strictly convex XY polygon_profile with 3..32 named vertices (x/y reference parameter IDs), and positive-Z extrude referencing an earlier profile and a height parameter. Either winding is accepted; repeated points, collinear corners and crossings are rejected. Cut size is the equal setback along X and Y (not diagonal face width). All number inputs are integer or fraction strings, e.g. '12' or '25/2'. Feature and parameter IDs are stable; face/edge indices are not persistent references. Inspect before planning. No generic fillets, holes, sketch constraint solving, booleans or curved surfaces yet."""
        return dispatch(store, {"action": "inspect"})

    @mcp.tool()
    def cad_preview(
        expected_revision: int, operations: list[Operation], preserve: list[str]
    ) -> dict:
        """Validate a proposed edit without saving. Preserve lists existing parameter IDs whose values must remain unchanged. Fixed constraints are enforced by Rust. Return structured diagnostics or proposed editable model and exact geometry. Inspect/replan on revision_conflict; explain unsupported geometry rather than substituting a mesh."""
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
