"""Verify real stdio tool negotiation and edits, without AI inference charges."""

import asyncio
import json
from pathlib import Path
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from store import ROOT


async def main():
    with tempfile.TemporaryDirectory() as directory:
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                str(Path(__file__).with_name("mcp_server.py")),
                "--store",
                str(Path(directory) / "demo.json"),
            ],
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                listing = await session.list_tools()
                assert {t.name for t in listing.tools} == {
                    "cad_inspect",
                    "cad_preview",
                    "cad_commit",
                    "cad_history",
                }

                async def call(name, args):
                    response = await session.call_tool(name, arguments=args)
                    assert not response.is_error, response
                    # Text JSON remains interoperable with clients that ignore structuredContent.
                    return json.loads(response.content[0].text)

                result = await call("cad_inspect", {})
                assert result["result"]["revision"] == 0
                create = json.loads((ROOT / "examples/ai-cad/create.json").read_text())
                create.pop("action")
                result = await call("cad_commit", create)
                assert result["result"]["bodies"][0]["volume_mm3"] == "71400"
                widen = json.loads((ROOT / "examples/ai-cad/widen.json").read_text())
                widen.pop("action")
                preview = {k: v for k, v in widen.items() if k != "transaction_id"}
                result = await call("cad_preview", preview)
                assert result["result"]["bodies"][0]["volume_mm3"] == "85800"
                assert (await call("cad_inspect", {}))["result"]["revision"] == 1
                result = await call("cad_commit", widen)
                assert result["result"]["revision"] == 2
                result = await call(
                    "cad_history",
                    {
                        "action": "undo",
                        "expected_revision": 2,
                        "transaction_id": "mcp-undo",
                    },
                )
                assert result["result"]["model"]["parameters"]["width"] == "100"
                invalid = await call(
                    "cad_preview",
                    {
                        "expected_revision": 3,
                        "preserve": [],
                        "operations": [
                            {"op": "set_parameter", "id": "thickness", "mm": "20"}
                        ],
                    },
                )
                assert invalid["error"]["code"] == "constraint_conflict"
                # Return to an empty model, then exercise the new discriminated
                # feature schemas through a real client/server transport.
                await call(
                    "cad_history",
                    {
                        "action": "undo",
                        "expected_revision": 3,
                        "transaction_id": "mcp-empty",
                    },
                )
                fixture = ROOT / "examples/ai-cad/profile-extrusion"
                for index, name in enumerate(("profile", "extrude", "widen")):
                    command = json.loads((fixture / f"{name}.json").read_text())
                    command.pop("action")
                    command["expected_revision"] = 4 + index
                    preview_args = {
                        k: v for k, v in command.items() if k != "transaction_id"
                    }
                    proposed = await call("cad_preview", preview_args)
                    assert "result" in proposed, proposed
                    result = (await call("cad_commit", command))["result"]
                    assert result["profiles"][0]["area_mm2"] == (
                        "5700" if name == "widen" else "4750"
                    )
                    if name == "profile":
                        assert result["bodies"] == []
                    else:
                        assert result["bodies"][0]["volume_mm3"] == (
                            "68400" if name == "widen" else "57000"
                        )
                invalid = await call(
                    "cad_preview",
                    {
                        "expected_revision": 7,
                        "preserve": [],
                        "operations": [
                            {"op": "set_parameter", "id": "tip_x", "mm": "200"}
                        ],
                    },
                )
                assert invalid["error"]["code"] == "invalid_profile"
                relationship = {
                    "op": "set_relation",
                    "id": "tip_x",
                    "relation": {"offset_mm": "0", "terms": {"width": "1/2"}},
                }
                result = await call(
                    "cad_commit",
                    {
                        "expected_revision": 7,
                        "transaction_id": "mcp-relation",
                        "operations": [relationship],
                        "preserve": ["width", "thickness"],
                    },
                )
                assert result["result"]["model"]["parameters"]["tip_x"] == "60"
                result = await call(
                    "cad_commit",
                    {
                        "expected_revision": 8,
                        "transaction_id": "mcp-related-widen",
                        "operations": [
                            {"op": "adjust_parameter", "id": "width", "delta_mm": "20"}
                        ],
                        "preserve": ["depth", "shoulder", "thickness", "zero"],
                    },
                )
                assert result["result"]["model"]["parameters"]["tip_x"] == "70"
                assert result["result"]["changed_parameters"] == ["tip_x", "width"]
                invalid = await call(
                    "cad_preview",
                    {
                        "expected_revision": 9,
                        "preserve": [],
                        "operations": [
                            {"op": "set_parameter", "id": "tip_x", "mm": "60"}
                        ],
                    },
                )
                assert invalid["error"]["code"] == "derived_parameter"
                result = await call(
                    "cad_history",
                    {
                        "action": "undo",
                        "expected_revision": 9,
                        "transaction_id": "mcp-relation-undo",
                    },
                )
                assert result["result"]["model"]["parameters"]["tip_x"] == "60"
                holes = [
                    {"op": "define_parameter", "id": "hole_x", "mm": "20"},
                    {"op": "define_parameter", "id": "hole_y", "mm": "15"},
                    {"op": "define_parameter", "id": "hole_radius", "mm": "3"},
                    {
                        "op": "add_feature",
                        "feature": {
                            "kind": "through_holes",
                            "id": "drilled",
                            "input": "plate",
                            "holes": [
                                {
                                    "id": "mount",
                                    "x": "hole_x",
                                    "y": "hole_y",
                                    "radius": "hole_radius",
                                }
                            ],
                        },
                    },
                ]
                # The profile fixture's extrusion ID is verified from inspection.
                extrusion = next(
                    f["id"]
                    for f in result["result"]["model"]["features"]
                    if f["kind"] == "extrude"
                )
                holes[-1]["feature"]["input"] = extrusion
                args = {
                    "expected_revision": 10,
                    "operations": holes,
                    "preserve": ["width", "thickness"],
                }
                proposed = await call("cad_preview", args)
                assert "analytic" in proposed["result"]["bodies"][0], proposed
                committed = await call(
                    "cad_commit", {**args, "transaction_id": "mcp-hole"}
                )
                assert committed["result"]["bodies"] == proposed["result"]["bodies"]
                invalid = await call(
                    "cad_preview",
                    {
                        "expected_revision": 11,
                        "operations": [
                            {"op": "set_parameter", "id": "hole_x", "mm": "3"}
                        ],
                        "preserve": [],
                    },
                )
                assert invalid["error"]["code"] == "hole_clearance"
                # A separate profile uses existing dimension references, exercising
                # the additive planar_profile discriminator over actual stdio.
                concave = {
                    "kind": "planar_profile",
                    "id": "concave",
                    "vertices": [
                        {"id": "a", "x": "zero", "y": "zero"},
                        {"id": "b", "x": "width", "y": "zero"},
                        {"id": "c", "x": "width", "y": "thickness"},
                        {"id": "d", "x": "thickness", "y": "thickness"},
                        {"id": "e", "x": "thickness", "y": "depth"},
                        {"id": "f", "x": "zero", "y": "depth"},
                    ],
                }
                args = {
                    "expected_revision": 11,
                    "preserve": [],
                    "operations": [
                        {"op": "add_feature", "feature": concave},
                        {
                            "op": "add_feature",
                            "feature": {
                                "kind": "extrude",
                                "id": "concave_solid",
                                "profile": "concave",
                                "height": "thickness",
                            },
                        },
                    ],
                }
                proposed = await call("cad_preview", args)
                assert "result" in proposed, proposed
                committed = await call(
                    "cad_commit", {**args, "transaction_id": "mcp-concave"}
                )
                assert committed["result"]["bodies"] == proposed["result"]["bodies"]
                assert any(
                    b.get("analytic", {}).get("kind") == "polygon_prism"
                    for b in committed["result"]["bodies"]
                )
                # Structural edits use the same revision/idempotency contract.
                replacement = dict(concave)
                replacement["vertices"] = list(reversed(concave["vertices"]))
                structural = {
                    "expected_revision": 12,
                    "preserve": [],
                    "operations": [
                        {
                            "op": "replace_feature",
                            "id": "concave",
                            "feature": replacement,
                        }
                    ],
                }
                proposed = await call("cad_preview", structural)
                assert "result" in proposed, proposed
                updated = await call(
                    "cad_commit", {**structural, "transaction_id": "mcp-replace"}
                )
                assert updated["result"]["bodies"] == proposed["result"]["bodies"]
                cleaned = await call(
                    "cad_commit",
                    {
                        "expected_revision": 13,
                        "transaction_id": "mcp-remove",
                        "preserve": [],
                        "operations": [
                            {"op": "remove_feature", "id": "concave"},
                            {"op": "remove_feature", "id": "concave_solid"},
                            {"op": "define_parameter", "id": "temporary", "mm": "1"},
                            {"op": "remove_parameter", "id": "temporary"},
                        ],
                    },
                )
                assert "result" in cleaned, cleaned
                assert "temporary" not in cleaned["result"]["model"]["parameters"]
                assert not any(
                    f["id"] == "concave" for f in cleaned["result"]["model"]["features"]
                )
                round_ops = [
                    {
                        "op": "add_feature",
                        "feature": {
                            "kind": "cylinder",
                            "id": "round_stock",
                            "x": "zero",
                            "y": "zero",
                            "radius": "width",
                            "height": "thickness",
                        },
                    },
                    {
                        "op": "add_feature",
                        "feature": {
                            "kind": "through_holes",
                            "id": "round_ring",
                            "input": "round_stock",
                            "holes": [
                                {
                                    "id": "center",
                                    "x": "zero",
                                    "y": "zero",
                                    "radius": "hole_radius",
                                }
                            ],
                        },
                    },
                ]
                round_result = await call(
                    "cad_commit",
                    {
                        "expected_revision": 14,
                        "transaction_id": "mcp-round",
                        "preserve": [],
                        "operations": round_ops,
                    },
                )
                assert "result" in round_result, round_result
                ring = next(
                    b
                    for b in round_result["result"]["bodies"]
                    if b["feature_id"] == "round_ring"
                )
                assert ring["analytic"]["kind"] == "round_prism"
                assert len(ring["analytic"]["holes"]) == 1
                assert "outer_circle" in ring["analytic"]
                blind_result = await call(
                    "cad_commit",
                    {
                        "expected_revision": 15,
                        "transaction_id": "mcp-blind",
                        "preserve": [],
                        "operations": [
                            {"op": "remove_feature", "id": "round_ring"},
                            {"op": "define_parameter", "id": "blind_depth", "mm": "1"},
                            {
                                "op": "add_feature",
                                "feature": {
                                    "kind": "blind_holes",
                                    "id": "round_pocket",
                                    "input": "round_stock",
                                    "depth": "blind_depth",
                                    "holes": [
                                        {
                                            "id": "center",
                                            "x": "zero",
                                            "y": "zero",
                                            "radius": "hole_radius",
                                        }
                                    ],
                                },
                            },
                        ],
                    },
                )
                assert "result" in blind_result, blind_result
                pocket = next(
                    b
                    for b in blind_result["result"]["bodies"]
                    if b["feature_id"] == "round_pocket"
                )
                assert pocket["analytic"]["hole_depth"] == "1"
                plane_result = await call(
                    "cad_commit",
                    {
                        "expected_revision": 16,
                        "transaction_id": "mcp-planes",
                        "preserve": [],
                        "operations": [
                            {"op": "define_parameter", "id": "cut_extent", "mm": "60"},
                            {
                                "op": "define_parameter",
                                "id": "cut_diagonal",
                                "mm": "60",
                            },
                            {"op": "define_parameter", "id": "cut_side", "mm": "-10"},
                            {
                                "op": "add_feature",
                                "feature": {
                                    "kind": "block",
                                    "id": "plane_stock",
                                    "width": "cut_extent",
                                    "depth": "cut_extent",
                                    "height": "cut_extent",
                                },
                            },
                            {
                                "op": "add_feature",
                                "feature": {
                                    "kind": "plane_cut",
                                    "id": "plane_one",
                                    "input": "plane_stock",
                                    "normal": ["1", "1", "1"],
                                    "offset": "cut_diagonal",
                                },
                            },
                            {
                                "op": "add_feature",
                                "feature": {
                                    "kind": "plane_cut",
                                    "id": "plane_two",
                                    "input": "plane_one",
                                    "normal": ["-1", "0", "0"],
                                    "offset": "cut_side",
                                },
                            },
                        ],
                    },
                )
                assert "result" in plane_result, plane_result
                plane = next(
                    b
                    for b in plane_result["result"]["bodies"]
                    if b["feature_id"] == "plane_two"
                )
                assert plane["volume_mm3"] == "62500/3"
                intersection_ops = [
                    {
                        "op": "add_feature",
                        "feature": {
                            "kind": "block",
                            "id": "intersection_stock",
                            "width": "cut_extent",
                            "depth": "cut_extent",
                            "height": "cut_extent",
                        },
                    },
                    {
                        "op": "add_feature",
                        "feature": {
                            "kind": "intersection",
                            "id": "common",
                            "left": "plane_two",
                            "right": "intersection_stock",
                        },
                    },
                ]
                intersection = await call(
                    "cad_preview",
                    {
                        "expected_revision": 17,
                        "operations": intersection_ops,
                        "preserve": [],
                    },
                )
                assert "result" in intersection, intersection
                common = next(
                    b
                    for b in intersection["result"]["bodies"]
                    if b["feature_id"] == "common"
                )
                assert common["volume_mm3"] == "62500/3"
                committed = await call(
                    "cad_commit",
                    {
                        "expected_revision": 17,
                        "transaction_id": "mcp-intersection",
                        "operations": intersection_ops,
                        "preserve": [],
                    },
                )
                assert committed["result"]["revision"] == 18
                assert not any(
                    b["feature_id"] in ["plane_two", "intersection_stock"]
                    for b in committed["result"]["bodies"]
                )

                move_operations = [
                    {
                        "op": "add_feature",
                        "feature": {
                            "kind": "translate",
                            "id": "moved_common",
                            "input": "common",
                            "offset": ["cut_side", "cut_extent", "cut_diagonal"],
                        },
                    }
                ]
                moved = await call(
                    "cad_preview",
                    {
                        "expected_revision": 18,
                        "operations": move_operations,
                        "preserve": [],
                    },
                )
                assert "result" in moved, moved
                body = next(
                    b
                    for b in moved["result"]["bodies"]
                    if b["feature_id"] == "moved_common"
                )
                assert body["volume_mm3"] == "62500/3"
                from fractions import Fraction

                before_points = {
                    tuple(Fraction(v) + d for v, d in zip(p, [-10, 60, 60]))
                    for p in common["boundary"]["vertices"]
                }
                assert {
                    tuple(map(Fraction, p)) for p in body["boundary"]["vertices"]
                } == before_points
                moved_commit = await call(
                    "cad_commit",
                    {
                        "expected_revision": 18,
                        "transaction_id": "mcp-move",
                        "operations": move_operations,
                        "preserve": [],
                    },
                )
                assert moved_commit["result"]["revision"] == 19
                turn_ops = [
                    {
                        "op": "add_feature",
                        "feature": {
                            "kind": "rotate_quarter",
                            "id": "turned_common",
                            "input": "moved_common",
                            "axis": "z",
                            "turns": 1,
                            "pivot": ["cut_side", "cut_extent", "cut_diagonal"],
                        },
                    }
                ]
                turned = await call(
                    "cad_preview",
                    {"expected_revision": 19, "operations": turn_ops, "preserve": []},
                )
                assert "result" in turned, turned
                rotated_body = next(
                    b
                    for b in turned["result"]["bodies"]
                    if b["feature_id"] == "turned_common"
                )
                assert rotated_body["volume_mm3"] == "62500/3"
                expected = {
                    (
                        Fraction(-10) - (Fraction(p[1]) - 60),
                        Fraction(60) + (Fraction(p[0]) + 10),
                        Fraction(p[2]),
                    )
                    for p in body["boundary"]["vertices"]
                }
                assert {
                    tuple(map(Fraction, p))
                    for p in rotated_body["boundary"]["vertices"]
                } == expected
                turn_commit = await call(
                    "cad_commit",
                    {
                        "expected_revision": 19,
                        "transaction_id": "mcp-turn",
                        "operations": turn_ops,
                        "preserve": [],
                    },
                )
                assert turn_commit["result"]["revision"] == 20

                print(
                    "PASS: stdio handshake, typed tool discovery, inspect, create, preview, widen, undo, profile/extrude schemas, exact relationships, analytic holes, convex intersection, exact movement, quarter turns and diagnostics"
                )


if __name__ == "__main__":
    asyncio.run(main())
