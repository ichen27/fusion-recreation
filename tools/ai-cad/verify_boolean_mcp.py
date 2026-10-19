"""Verify the typed planar Boolean operation through a real MCP stdio session."""

import argparse
import asyncio
import copy
import json
from pathlib import Path
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from store import ROOT, Store
from test_booleans import cases
from test_intersection import operations

EXAMPLE = ROOT / "examples/ai-cad/planar-booleans"


async def main(write=False):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "model.json"
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("mcp_server.py")), "--store", str(path)],
        )
        async with stdio_client(params) as (read, output):
            async with ClientSession(read, output) as session:
                await session.initialize()
                schemas = await session.list_tools()
                assert "BooleanSolid" in json.dumps(
                    [t.model_dump() for t in schemas.tools]
                )
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

                model, _, _ = cases()["through"]
                args = dict(
                    expected_revision=0, operations=operations(model), preserve=[]
                )
                proposed = await call("cad_preview", args)
                assert proposed["result"]["bodies"][0]["volume_mm3"] == "640", proposed
                assert not path.exists()
                committed = await call(
                    "cad_commit", {**args, "transaction_id": "boolean-through"}
                )
                assert committed["result"]["bodies"] == proposed["result"]["bodies"]
                if write:
                    (EXAMPLE / "mcp-through.cad.json").write_bytes(path.read_bytes())
                args = dict(
                    expected_revision=1,
                    operations=[
                        dict(
                            op="replace_feature",
                            id="result",
                            feature={
                                **model["features"][-1],
                                "operation": "intersection",
                            },
                        )
                    ],
                    preserve=list(model["parameters"]),
                )
                proposed = await call("cad_preview", args)
                assert proposed["result"]["bodies"][0]["volume_mm3"] == "360"
                committed = await call(
                    "cad_commit", {**args, "transaction_id": "boolean-intersection"}
                )
                assert committed["result"]["bodies"] == proposed["result"]["bodies"]
                before = path.read_bytes()
                stale = await call(
                    "cad_commit", {**args, "transaction_id": "boolean-stale"}
                )
                assert stale["error"]["code"] == "revision_conflict"
                assert path.read_bytes() == before
                if write:
                    (EXAMPLE / "mcp-intersection.cad.json").write_bytes(before)
                reopened = Store(path).execute({"action": "inspect"})
                assert reopened["bodies"] == committed["result"]["bodies"]
                if write:
                    (EXAMPLE / "mcp-recording.json").write_text(
                        json.dumps({"calls": calls}, indent=2) + "\n"
                    )
    print(
        "PASS: typed Boolean MCP discovery, previews, commits, operation replacement, stale rejection and native reopen"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
