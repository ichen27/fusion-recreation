"""Actual shared-command edits of independent geometry branches and undo."""

import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from benchmark_independent_rebuild import model
from store import ROOT
from test_intersection import operations

EXAMPLE = ROOT / "examples/ai-cad/independent-rebuild"


async def main(write=False):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.cad.json"
        calls = []
        snapshots = {}
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("mcp_server.py")), "--store", str(path)],
        )
        async with stdio_client(params) as (read, output):
            async with ClientSession(read, output) as session:
                await session.initialize()

                async def call(name, arguments):
                    raw = await session.call_tool(name, arguments)
                    reply = json.loads(
                        next(c.text for c in raw.content if c.type == "text")
                    )
                    calls.append(dict(tool=name, arguments=arguments, reply=reply))
                    return reply

                created = await call(
                    "cad_commit",
                    dict(
                        expected_revision=0,
                        transaction_id="create",
                        operations=operations(model()),
                        preserve=[],
                    ),
                )
                assert [b["volume_mm3"] for b in created["result"]["bodies"]] == [
                    "784"
                ] * 4
                snapshots["source"] = path.read_bytes()
                edit = dict(
                    expected_revision=1,
                    operations=[dict(op="set_parameter", id="p0.a.height", mm="11")],
                    preserve=[f"p{i}.a.height" for i in range(1, 4)],
                )
                preview = await call("cad_preview", edit)
                assert [b["volume_mm3"] for b in preview["result"]["bodies"]] == [
                    "884",
                    "784",
                    "784",
                    "784",
                ]
                assert path.read_bytes() == snapshots["source"]
                saved = await call("cad_commit", {**edit, "transaction_id": "taller"})
                assert saved["result"]["model"] == preview["result"]["model"]
                snapshots["edited"] = path.read_bytes()
                invalid = await call(
                    "cad_preview",
                    dict(
                        expected_revision=2,
                        operations=[dict(op="set_parameter", id="p0.a.height", mm="0")],
                        preserve=[],
                    ),
                )
                assert "error" in invalid
                assert path.read_bytes() == snapshots["edited"]
                undone = await call(
                    "cad_history",
                    dict(action="undo", expected_revision=2, transaction_id="undo"),
                )
                assert undone["result"]["model"] == created["result"]["model"]
                snapshots["undo"] = path.read_bytes()
        if write:
            EXAMPLE.mkdir(parents=True, exist_ok=True)
            (EXAMPLE / "mcp-recording.json").write_text(
                json.dumps(dict(calls=calls), indent=2) + "\n"
            )
            for name, data in snapshots.items():
                (EXAMPLE / f"{name}.cad.json").write_bytes(data)
    print(
        f"PASS: {len(calls)} actual MCP calls, independent branches, atomic rejection and undo"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
