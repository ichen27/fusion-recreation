"""Actual typed MCP separation, contact, overlap, stale reads and history."""

import argparse
import asyncio
import copy
import json
from pathlib import Path
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from store import ROOT
from test_intersection import rectangle, operations
from test_instances import instance

EXAMPLE = ROOT / "examples/ai-cad/clearance"


async def main(write=False):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        calls = []
        snapshots = {}
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("mcp_server.py")), "--store", str(path)],
        )
        async with stdio_client(params) as (read, output):
            async with ClientSession(read, output) as session:
                await session.initialize()
                assert "cad_clearance" in {
                    t.name for t in (await session.list_tools()).tools
                }

                async def call(name, args):
                    raw = await session.call_tool(name, args)
                    reply = json.loads(
                        next(c.text for c in raw.content if c.type == "text")
                    )
                    calls.append(
                        dict(tool=name, arguments=copy.deepcopy(args), reply=reply)
                    )
                    return reply

                model = instance(rectangle("part", 0, 0, 10, 4, 2), offset=(13, 8, 2))
                assert "result" in await call(
                    "cad_commit",
                    dict(
                        expected_revision=0,
                        transaction_id="create",
                        operations=operations(model),
                        preserve=[],
                    ),
                )
                snapshots["source"] = path.read_bytes()
                base = dict(expected_revision=1, left="part", right="copy")
                result = (await call("cad_clearance", base))["result"]
                assert (
                    result["relation"] == "separated" and result["distance_mm"] == "5"
                )
                assert path.read_bytes() == snapshots["source"]
                for revision, name, offset, relation in [
                    (1, "contact", (10, 0, 0), "touching"),
                    (2, "overlap", (5, 0, 0), "overlapping"),
                ]:
                    edit = dict(
                        expected_revision=revision,
                        operations=[
                            dict(op="set_parameter", id="copy." + axis, mm=str(value))
                            for axis, value in zip("xyz", offset)
                        ],
                        preserve=[],
                    )
                    assert "result" in await call("cad_preview", edit)
                    assert "result" in await call(
                        "cad_commit", {**edit, "transaction_id": name}
                    )
                    snapshots[name] = path.read_bytes()
                    stale = await call(
                        "cad_clearance", {**base, "expected_revision": revision}
                    )
                    assert stale["error"]["code"] == "revision_conflict"
                    result = (
                        await call(
                            "cad_clearance", {**base, "expected_revision": revision + 1}
                        )
                    )["result"]
                    assert (
                        result["relation"] == relation and result["distance_mm"] == "0"
                    )
                    assert (result["closest_points_mm"] is None) == (
                        relation == "overlapping"
                    )
                    assert path.read_bytes() == snapshots[name]
                assert "result" in await call(
                    "cad_history",
                    dict(action="undo", expected_revision=3, transaction_id="undo"),
                )
                snapshots["undo"] = path.read_bytes()
                result = (
                    await call("cad_clearance", {**base, "expected_revision": 4})
                )["result"]
                assert (
                    result["relation"] == "touching"
                    and path.read_bytes() == snapshots["undo"]
                )
        if write:
            EXAMPLE.mkdir(parents=True, exist_ok=True)
            for name, data in snapshots.items():
                (EXAMPLE / (name + ".cad.json")).write_bytes(data)
            (EXAMPLE / "mcp-recording.json").write_text(
                json.dumps(dict(calls=calls), indent=2) + "\n"
            )
    print(
        f"PASS: {len(calls)} actual MCP calls, exact separation/contact/overlap, stale rejection and native undo"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
