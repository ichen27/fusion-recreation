"""Actual MCP linked placement and source-dimension propagation."""

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
from test_intersection import operations
from test_instances import instance

EXAMPLE = ROOT / "examples/ai-cad/linked-instances"


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

                inputs = l_shape()
                linked = instance(inputs)
                steps = [
                    ("input", operations(inputs), ["204"]),
                    (
                        "pair",
                        [
                            dict(op="define_parameter", id=k, mm=v)
                            for k, v in linked["parameters"].items()
                            if k not in inputs["parameters"]
                        ]
                        + [dict(op="add_feature", feature=linked["features"][-1])],
                        ["204", "204"],
                    ),
                    (
                        "edited",
                        [
                            dict(
                                op="set_parameter",
                                id=inputs["features"][-1]["height"],
                                mm="6",
                            )
                        ],
                        ["306", "306"],
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
                        operations=[dict(op="remove_feature", id="l")],
                        preserve=[],
                    ),
                )
                assert rejected["error"]["code"] == "unsupported_reference"
                assert path.read_bytes() == before
                if write:
                    (EXAMPLE / "mcp-recording.json").write_text(
                        json.dumps({"calls": calls}, indent=2) + "\n"
                    )
    print(
        "PASS: seven actual MCP calls, linked placement, shared source edit and source-deletion rejection"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
