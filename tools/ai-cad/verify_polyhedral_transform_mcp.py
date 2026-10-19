"""Exercise nonconvex movement and quarter turns over the actual typed MCP tools."""

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
from test_booleans import cases
from test_intersection import operations
from test_polyhedral_transforms import moved, turned

EXAMPLE = ROOT / "examples/ai-cad/planar-transforms"


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
                    body = json.loads(
                        next(c.text for c in reply.content if c.type == "text")
                    )
                    calls.append(
                        dict(
                            tool=name,
                            arguments=copy.deepcopy(args),
                            reply=copy.deepcopy(body),
                        )
                    )
                    return body

                original = cases()["through"][0]
                stages = [
                    ("through", original),
                    ("moved", moved(original, (10, -5, 3))),
                    (
                        "turned",
                        turned(moved(original, (10, -5, 3)), "x", 1, (10, -5, 3)),
                    ),
                ]
                previous = {"parameters": {}, "features": []}
                for revision, (name, model) in enumerate(stages):
                    added = {
                        "parameters": {
                            k: v
                            for k, v in model["parameters"].items()
                            if k not in previous["parameters"]
                        },
                        "features": model["features"][len(previous["features"]) :],
                    }
                    args = dict(
                        expected_revision=revision,
                        operations=operations(added),
                        preserve=list(previous["parameters"]),
                    )
                    before = path.read_bytes() if path.exists() else None
                    preview = await call("cad_preview", args)
                    assert preview["result"]["bodies"][0]["volume_mm3"] == "640", (
                        preview
                    )
                    assert (path.read_bytes() if path.exists() else None) == before
                    saved = await call(
                        "cad_commit", {**args, "transaction_id": "mcp-" + name}
                    )
                    assert saved["result"]["bodies"] == preview["result"]["bodies"]
                    if write:
                        (EXAMPLE / ("mcp-" + name + ".cad.json")).write_bytes(
                            path.read_bytes()
                        )
                    previous = model
                before = path.read_bytes()
                rejected = await call(
                    "cad_preview",
                    dict(
                        expected_revision=3,
                        operations=[
                            dict(op="set_parameter", id="turn.x", mm="1000001")
                        ],
                        preserve=[],
                    ),
                )
                assert rejected["error"]["code"] == "rotation_range"
                assert path.read_bytes() == before
                if write:
                    (EXAMPLE / "mcp-recording.json").write_text(
                        json.dumps({"calls": calls}, indent=2) + "\n"
                    )
    print(
        "PASS: seven actual MCP calls, holed-solid move/turn, unchanged volumes and atomic pivot-range rejection"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
