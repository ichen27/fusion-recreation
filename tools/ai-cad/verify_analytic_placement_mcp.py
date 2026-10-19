"""Actual MCP analytic placement, quarter turns and atomic depth rejection."""

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
from test_round_stock import flange
from test_blind_holes import blind
from test_intersection import operations
from test_polyhedral_transforms import moved, turned

EXAMPLE = ROOT / "examples/ai-cad/analytic-placement"


async def main(write=False):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("mcp_server.py")), "--store", str(path)],
        )
        async with stdio_client(params) as (read, output):
            async with ClientSession(read, output) as session:
                await session.initialize()
                calls = []

                async def call(name, args):
                    reply = await session.call_tool(name, args)
                    value = json.loads(
                        next(c.text for c in reply.content if c.type == "text")
                    )
                    calls.append(
                        dict(
                            tool=name,
                            arguments=copy.deepcopy(args),
                            reply=copy.deepcopy(value),
                        )
                    )
                    return value

                inputs = blind(flange())
                translated = moved(inputs, (10, -5, 3))
                oriented = turned(translated, "x", 1)
                steps = [("input", operations(inputs), ["7764*pi"])]
                for name, previous, current in [
                    ("moved", inputs, translated),
                    ("turned", translated, oriented),
                ]:
                    ops = [
                        dict(op="define_parameter", id=k, mm=v)
                        for k, v in current["parameters"].items()
                        if k not in previous["parameters"]
                    ]
                    ops.append(dict(op="add_feature", feature=current["features"][-1]))
                    steps.append((name, ops, ["7764*pi"]))
                for revision, (name, ops, volumes) in enumerate(steps):
                    args = dict(expected_revision=revision, operations=ops, preserve=[])
                    before = path.read_bytes() if path.exists() else None
                    preview = await call("cad_preview", args)
                    assert [
                        b["volume_mm3"] for b in preview["result"]["bodies"]
                    ] == volumes, preview
                    assert (path.read_bytes() if path.exists() else None) == before
                    saved = await call(
                        "cad_commit", {**args, "transaction_id": "mcp-" + name}
                    )
                    assert saved["result"]["bodies"] == preview["result"]["bodies"]
                    if write:
                        (EXAMPLE / ("mcp-" + name + ".cad.json")).write_bytes(
                            path.read_bytes()
                        )
                before = path.read_bytes()
                rejected = await call(
                    "cad_preview",
                    dict(
                        expected_revision=3,
                        operations=[dict(op="set_parameter", id="depth", mm="5")],
                        preserve=[],
                    ),
                )
                assert rejected["error"]["code"] == "hole_depth"
                assert path.read_bytes() == before
                if write:
                    (EXAMPLE / "mcp-recording.json").write_text(
                        json.dumps({"calls": calls}, indent=2) + "\n"
                    )
    print(
        "PASS: seven actual MCP calls, exact analytic movement/quarter-turn and invalid blind-depth rejection"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
