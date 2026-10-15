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
                print(
                    "PASS: stdio handshake, typed tool discovery, inspect, create, preview, widen, undo, diagnostics"
                )


if __name__ == "__main__":
    asyncio.run(main())
