"""Record typed MCP cavity creation, plane editing and empty-result rejection."""

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
from test_polyhedral_cuts import cut

EXAMPLE = ROOT / "examples/ai-cad/nonconvex-plane-cuts"


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
                    content = json.loads(
                        next(c.text for c in reply.content if c.type == "text")
                    )
                    calls.append(
                        dict(
                            tool=name,
                            arguments=copy.deepcopy(args),
                            reply=copy.deepcopy(content),
                        )
                    )
                    return content

                original = cases()["cavity"][0]
                trimmed = cut(original)
                steps = [
                    ("input", operations(original), 784),
                    (
                        "opened",
                        [
                            dict(op="define_parameter", id="trimmed.offset", mm="5"),
                            dict(op="add_feature", feature=trimmed["features"][-1]),
                        ],
                        392,
                    ),
                    (
                        "lowered",
                        [dict(op="set_parameter", id="trimmed.offset", mm="4")],
                        328,
                    ),
                ]
                for revision, (name, ops, volume) in enumerate(steps):
                    args = dict(expected_revision=revision, operations=ops, preserve=[])
                    before = path.read_bytes() if path.exists() else None
                    preview = await call("cad_preview", args)
                    assert preview["result"]["bodies"][0]["volume_mm3"] == str(
                        volume
                    ), preview
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
                            dict(op="set_parameter", id="trimmed.offset", mm="0")
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
        "PASS: seven actual MCP calls, cavity-to-pocket cut, depth edit and atomic empty-result rejection"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
