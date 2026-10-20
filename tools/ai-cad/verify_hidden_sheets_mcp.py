"""Actual typed planar hidden-line exports, explicit curved rejection and undo."""

import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from store import ROOT
from test_booleans import cases
from test_interference import pair
from test_round_stock import cylinder
from test_intersection import operations

EXAMPLE = ROOT / "examples/ai-cad/hidden-line-sheets"


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

                model = pair(cases()["cavity"][0], cylinder(radius="1", height="2"))
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
                    "cad_reference_sheet",
                    dict(
                        expected_revision=1, feature_id="result", style="planar_hidden"
                    ),
                )
                assert first["result"]["representation"] == "orthographic_planar_hidden"
                assert all(
                    v["hidden_segments"] > 0 and v["visible_segments"] > 0
                    for v in first["result"]["views"]
                )
                files["source.svg"] = first["result"]["svg"].encode()
                wire = await call(
                    "cad_reference_sheet",
                    dict(expected_revision=1, feature_id="result"),
                )
                assert wire["result"]["representation"] == "orthographic_all_edges"
                files["all-edges.svg"] = wire["result"]["svg"].encode()
                rejected = await call(
                    "cad_reference_sheet",
                    dict(
                        expected_revision=1, feature_id="stock", style="planar_hidden"
                    ),
                )
                assert rejected["error"]["code"] == "unsupported_drawing"
                assert path.read_bytes() == files["source.cad.json"]
                await call(
                    "cad_commit",
                    dict(
                        expected_revision=1,
                        transaction_id="cavity-height",
                        operations=[dict(op="set_parameter", id="b.height", mm="4")],
                        preserve=[],
                    ),
                )
                files["edited.cad.json"] = path.read_bytes()
                second = await call(
                    "cad_reference_sheet",
                    dict(
                        expected_revision=2, feature_id="result", style="planar_hidden"
                    ),
                )
                assert (
                    second["result"]["source_model_sha256"]
                    != first["result"]["source_model_sha256"]
                )
                assert second["result"]["extents_mm"] == ["10"] * 3
                files["edited.svg"] = second["result"]["svg"].encode()
                undone = await call(
                    "cad_history",
                    dict(action="undo", expected_revision=2, transaction_id="undo"),
                )
                assert undone["result"]["model"] == created["result"]["model"]
                files["undo.cad.json"] = path.read_bytes()
                last = await call(
                    "cad_reference_sheet",
                    dict(
                        expected_revision=3, feature_id="result", style="planar_hidden"
                    ),
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
        f"PASS: {len(calls)} actual MCP calls, planar hidden/all-edge styles, curved rejection, source edit and undo"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
