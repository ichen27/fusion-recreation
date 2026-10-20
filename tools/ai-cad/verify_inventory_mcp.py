"""Actual typed inventory reads through preview, source edit, stale read and undo."""

import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from store import ROOT
from test_booleans import box
from test_instances import instance
from test_interference import pair
from test_intersection import operations
from test_materials import assign
from test_round_stock import cylinder

EXAMPLE = ROOT / "examples/ai-cad/inventory"


def fixture():
    source = instance(box("plate", [0, 0, 0], [10, 4, 2]), offset=(20, 0, 0))
    source = pair(source, box("block", [40, 0, 0], [45, 8, 2]))
    return pair(source, cylinder(cx="60", radius="3", height="2"))


async def main(write=False):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "inventory.cad.json"
        calls, files = [], {}
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("mcp_server.py")), "--store", str(path)],
        )
        async with stdio_client(params) as (read, output):
            async with ClientSession(read, output) as session:
                await session.initialize()

                async def call(tool, args, error=None):
                    before = path.read_bytes() if path.exists() else None
                    raw = await session.call_tool(tool, args)
                    reply = json.loads(
                        next(c.text for c in raw.content if c.type == "text")
                    )
                    calls.append(dict(tool=tool, arguments=args, reply=reply))
                    if tool in ("cad_inventory", "cad_preview"):
                        assert path.read_bytes() == before
                    if error:
                        assert reply["error"]["code"] == error
                        return reply
                    assert "error" not in reply, reply
                    return reply["result"]

                await call(
                    "cad_commit",
                    dict(
                        expected_revision=0,
                        transaction_id="create",
                        operations=operations(fixture())
                        + [
                            assign("plate", "Sample alloy", "1000"),
                            assign("stock", "Turned stock", "2000"),
                        ],
                        preserve=[],
                    ),
                )
                files["source.cad.json"] = path.read_bytes()
                first = await call("cad_inventory", dict(expected_revision=1))
                assert first["solid_count"] == 4 and first["material_counts"] == dict(
                    assigned=3, unassigned=1, conflict=0
                )
                assert [r["volume_mm3"] for r in first["rows"]] == [
                    "80",
                    "80",
                    "80",
                    "18*pi",
                ]
                edit = dict(
                    expected_revision=1,
                    operations=[dict(op="set_parameter", id="plate.height", mm="3")],
                    preserve=[],
                )
                await call("cad_preview", edit)
                assert await call("cad_inventory", dict(expected_revision=1)) == first
                await call("cad_commit", {**edit, "transaction_id": "height"})
                files["edited.cad.json"] = path.read_bytes()
                changed = await call("cad_inventory", dict(expected_revision=2))
                assert [r["volume_mm3"] for r in changed["rows"]] == [
                    "80",
                    "120",
                    "120",
                    "18*pi",
                ]
                await call(
                    "cad_inventory",
                    dict(expected_revision=1),
                    error="revision_conflict",
                )
                await call(
                    "cad_history",
                    dict(action="undo", expected_revision=2, transaction_id="undo"),
                )
                files["undo.cad.json"] = path.read_bytes()
                restored = await call("cad_inventory", dict(expected_revision=3))
                assert (
                    restored["rows"] == first["rows"]
                    and restored["source_model_sha256"] == first["source_model_sha256"]
                )
                files["source.csv"] = first["csv"].encode()
                files["source.json"] = (
                    json.dumps({k: v for k, v in first.items() if k != "csv"}, indent=2)
                    + "\n"
                ).encode()
                files["edited.csv"] = changed["csv"].encode()
                files["edited.json"] = (
                    json.dumps(
                        {k: v for k, v in changed.items() if k != "csv"}, indent=2
                    )
                    + "\n"
                ).encode()
        if write:
            EXAMPLE.mkdir(parents=True, exist_ok=True)
            for name, data in files.items():
                (EXAMPLE / name).write_bytes(data)
            (EXAMPLE / "mcp-recording.json").write_text(
                json.dumps(dict(calls=calls), indent=2) + "\n"
            )
    print(
        f"PASS: {len(calls)} actual MCP calls; separate identities/exact volumes/material status; preview isolation, edits, stale rejection and undo"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
