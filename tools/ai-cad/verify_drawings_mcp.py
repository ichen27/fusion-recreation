"""Actual typed reference-sheet creation, source edit and history checks."""

import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from store import ROOT
from test_holes import perforated
from test_intersection import operations

EXAMPLE = ROOT / "examples/ai-cad/reference-sheets"


async def main(write=False):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.cad.json"
        calls = []
        files = {}
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

                model = perforated()
                created = await call(
                    "cad_commit",
                    dict(
                        expected_revision=0,
                        transaction_id="create",
                        operations=operations(model),
                        preserve=[],
                    ),
                )
                files["source.cad.json"] = path.read_bytes()
                first = await call(
                    "cad_reference_sheet", dict(expected_revision=1, feature_id="part")
                )
                assert first["result"]["extents_mm"] == ["100", "60", "6"]
                files["source.svg"] = first["result"]["svg"].encode()
                assert path.read_bytes() == files["source.cad.json"]
                edit = dict(
                    expected_revision=1,
                    operations=[
                        dict(
                            op="set_parameter",
                            id=model["features"][1]["height"],
                            mm="12",
                        )
                    ],
                    preserve=[],
                )
                await call("cad_preview", edit)
                assert path.read_bytes() == files["source.cad.json"]
                await call("cad_commit", {**edit, "transaction_id": "thicker"})
                files["edited.cad.json"] = path.read_bytes()
                second = await call(
                    "cad_reference_sheet", dict(expected_revision=2, feature_id="part")
                )
                assert second["result"]["extents_mm"] == ["100", "60", "12"]
                assert (
                    second["result"]["source_model_sha256"]
                    != first["result"]["source_model_sha256"]
                )
                files["edited.svg"] = second["result"]["svg"].encode()
                stale = await call(
                    "cad_reference_sheet", dict(expected_revision=1, feature_id="part")
                )
                assert stale["error"]["code"] == "revision_conflict"
                assert path.read_bytes() == files["edited.cad.json"]
                undone = await call(
                    "cad_history",
                    dict(action="undo", expected_revision=2, transaction_id="undo"),
                )
                assert undone["result"]["model"] == created["result"]["model"]
                files["undo.cad.json"] = path.read_bytes()
                last = await call(
                    "cad_reference_sheet", dict(expected_revision=3, feature_id="part")
                )
                assert (
                    last["result"]["source_model_sha256"]
                    == first["result"]["source_model_sha256"]
                )
                files["undo.svg"] = last["result"]["svg"].encode()
        if write:
            EXAMPLE.mkdir(parents=True, exist_ok=True)
            for name, data in files.items():
                (EXAMPLE / name).write_bytes(data)
            (EXAMPLE / "mcp-recording.json").write_text(
                json.dumps(dict(calls=calls), indent=2) + "\n"
            )
    print(
        f"PASS: {len(calls)} actual MCP calls, native circular drawing views, source edits, stale revision and undo"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
