"""Actual MCP calls admit concave extrusion into Boolean and transform operations."""

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
from test_concave_operations import l_shape
from test_intersection import rectangle, operations
from test_booleans import boolean
from test_polyhedral_transforms import moved

EXAMPLE = ROOT / "examples/ai-cad/concave-operations"


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

                joined = boolean(
                    l_shape(), rectangle("b", 2, 2, 4, 4, 4), "intersection"
                )
                inputs = copy.deepcopy(joined)
                inputs["features"].pop()
                moved_model = moved(joined)
                steps = [
                    ("inputs", operations(inputs), ["64", "204"]),
                    (
                        "common",
                        [dict(op="add_feature", feature=joined["features"][-1])],
                        ["28"],
                    ),
                    (
                        "moved",
                        [
                            dict(op="define_parameter", id=k, mm=v)
                            for k, v in moved_model["parameters"].items()
                            if k not in joined["parameters"]
                        ]
                        + [dict(op="add_feature", feature=moved_model["features"][-1])],
                        ["28"],
                    ),
                ]
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
                        operations=[
                            dict(op="define_parameter", id="zero", mm="0"),
                            dict(
                                op="add_feature",
                                feature=dict(
                                    kind="plane_cut",
                                    id="empty",
                                    input="moved",
                                    normal=["0", "0", "1"],
                                    offset="zero",
                                ),
                            ),
                        ],
                        preserve=[],
                    ),
                )
                assert rejected["error"]["code"] == "empty_solid"
                assert path.read_bytes() == before
                if write:
                    (EXAMPLE / "mcp-recording.json").write_text(
                        json.dumps({"calls": calls}, indent=2) + "\n"
                    )
    print(
        "PASS: seven actual MCP calls, concave-profile Boolean, movement and empty-cut rejection"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
