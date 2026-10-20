"""Exercise exact dimension entry through a real isolated stdio MCP server."""

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
from test_dimension_input import create

EXAMPLE = ROOT / "examples/ai-cad/dimensions"


async def main(write=False):
    calls = []
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("mcp_server.py")), "--store", str(path)],
        )
        async with stdio_client(params) as (read, output):
            async with ClientSession(read, output) as session:
                await session.initialize()

                async def call(name, args):
                    raw = await session.call_tool(name, args)
                    reply = json.loads(
                        next(c.text for c in raw.content if c.type == "text")
                    )
                    calls.append(
                        dict(tool=name, arguments=copy.deepcopy(args), reply=reply)
                    )
                    return reply

                command = create()
                command.pop("action")
                command.pop("transaction_id")
                assert "result" in await call("cad_preview", command)
                assert not path.exists()
                result = await call(
                    "cad_commit", {**command, "transaction_id": "create"}
                )
                assert result["result"]["model"]["parameters"]["width"] == "127/10"
                original = path.read_bytes()
                measure = await call(
                    "cad_measure", dict(expected_revision=1, feature_id="stock")
                )
                assert "result" in measure
                edit = dict(
                    expected_revision=1,
                    operations=[
                        dict(op="adjust_parameter", id="width", delta_mm="-1/4 in")
                    ],
                    preserve=["depth", "height"],
                )
                assert "result" in await call("cad_preview", edit)
                assert path.read_bytes() == original
                result = await call("cad_commit", {**edit, "transaction_id": "edit"})
                assert result["result"]["model"]["parameters"]["width"] == "127/20"
                changed = path.read_bytes()
                bad = await call(
                    "cad_preview",
                    dict(
                        expected_revision=2,
                        operations=[dict(op="set_parameter", id="width", mm="1 yd")],
                        preserve=[],
                    ),
                )
                assert (
                    bad["error"]["code"] == "invalid_number"
                    and path.read_bytes() == changed
                )
                preserved = await call(
                    "cad_preview",
                    dict(
                        expected_revision=2,
                        operations=[dict(op="set_parameter", id="width", mm="1 in")],
                        preserve=["width"],
                    ),
                )
                assert (
                    preserved["error"]["code"] == "preserve_conflict"
                    and path.read_bytes() == changed
                )
                assert "result" in await call(
                    "cad_history",
                    dict(action="undo", expected_revision=2, transaction_id="undo"),
                )
                assert (
                    Store(path).execute(dict(action="inspect"))["model"]
                    == json.loads(original)["state"]["model"]
                )
        if write:
            EXAMPLE.mkdir(parents=True, exist_ok=True)
            for name, data in [
                ("mcp-created.cad.json", original),
                ("mcp-edited.cad.json", changed),
                ("mcp-undo.cad.json", path.read_bytes()),
            ]:
                (EXAMPLE / name).write_bytes(data)
            (EXAMPLE / "mcp-recording.json").write_text(
                json.dumps(dict(calls=calls), indent=2) + "\n"
            )
    print(
        "PASS: eight actual typed MCP calls; exact units, measurement, preview/commit, rejection and undo"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
