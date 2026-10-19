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
                print(
                    "PASS: stdio handshake, typed tool discovery, inspect, create, preview, widen, undo, profile/extrude schemas, exact relationships, analytic holes and diagnostics"
                )


if __name__ == "__main__":
    asyncio.run(main())
