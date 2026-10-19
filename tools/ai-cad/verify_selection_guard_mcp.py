"""Actual MCP guards reject changed context and preserve receipt retry semantics."""

import asyncio
import json
from pathlib import Path
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from store import Store
from test_counterbores import counterbored
from test_intersection import operations


async def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        Store(path).execute(
            dict(
                action="commit",
                expected_revision=0,
                transaction_id="seed",
                operations=operations(counterbored()),
                preserve=[],
            )
        )
        before = path.read_bytes()
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("mcp_server.py")), "--store", str(path)],
        )
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()

                async def call(name, args):
                    raw = await session.call_tool(name, args)
                    return json.loads(
                        next(c.text for c in raw.content if c.type == "text")
                    )

                async def select(hole):
                    result = await call(
                        "cad_select_surface",
                        dict(
                            expected_revision=1,
                            feature_id="part",
                            surface_id=f"feature/part/hole/{hole}/upper",
                        ),
                    )
                    assert "result" in result

                await select("left")
                command = dict(
                    expected_revision=1,
                    operations=[dict(op="set_parameter", id="recess_radius", mm="6")],
                    preserve=[],
                    selection_guard=dict(
                        feature_id="part", surface_id="feature/part/hole/left/upper"
                    ),
                )
                assert "result" in await call("cad_preview", command)
                await select("right")
                commit = {**command, "transaction_id": "guarded"}
                rejected = await call("cad_commit", commit)
                assert rejected["error"]["code"] == "selection_conflict"
                assert path.read_bytes() == before
                await select("left")
                assert (await call("cad_commit", commit))["result"]["revision"] == 2
                after = path.read_bytes()
                replay = await call("cad_commit", commit)
                assert (
                    replay["result"]["replayed"]
                    and replay["result"]["committed_revision"] == 2
                )
                assert path.read_bytes() == after
    print(
        "PASS: seven actual MCP calls; guarded preview, changed selection rejection, explicit reselect, commit and idempotent retry"
    )


if __name__ == "__main__":
    asyncio.run(main())
