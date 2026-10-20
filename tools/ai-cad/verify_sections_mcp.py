"""Actual typed cross-section reads, explicit failures and source edit/undo."""

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

EXAMPLE = ROOT / "examples/ai-cad/planar-sections"


async def main(write=False):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.cad.json"
        calls, files = [], {}
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
                await call(
                    "cad_commit",
                    dict(
                        expected_revision=0,
                        transaction_id="create",
                        operations=operations(model),
                        preserve=[],
                    ),
                )
                files["source.cad.json"] = path.read_bytes()
                command = dict(
                    expected_revision=1, feature_id="result", axis="Y", offset_mm="5"
                )
                first = await call("cad_section", command)
                assert first["result"]["area_mm2"] == "64"
                assert first["result"]["centroid_mm"] == ["5"] * 3
                files["source.svg"] = first["result"]["svg"].encode()
                for extra, code in [
                    ({"offset_mm": "2"}, "section_degenerate"),
                    ({"offset_mm": "12"}, "empty_section"),
                    ({"feature_id": "stock"}, "unsupported_section"),
                ]:
                    reply = await call("cad_section", {**command, **extra})
                    assert reply["error"]["code"] == code
                assert path.read_bytes() == files["source.cad.json"]
                await call(
                    "cad_commit",
                    dict(
                        expected_revision=1,
                        transaction_id="shorter-cavity",
                        operations=[dict(op="set_parameter", id="b.height", mm="4")],
                        preserve=[],
                    ),
                )
                files["edited.cad.json"] = path.read_bytes()
                second = await call("cad_section", {**command, "expected_revision": 2})
                assert second["result"]["area_mm2"] == "76"
                assert second["result"]["centroid_mm"] == ["5", "5", "101/19"]
                files["edited.svg"] = second["result"]["svg"].encode()
                stale = await call("cad_section", command)
                assert stale["error"]["code"] == "revision_conflict"
                assert path.read_bytes() == files["edited.cad.json"]
                await call(
                    "cad_history",
                    dict(action="undo", expected_revision=2, transaction_id="undo"),
                )
                files["undo.cad.json"] = path.read_bytes()
                last = await call("cad_section", {**command, "expected_revision": 3})
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
        f"PASS: {len(calls)} actual MCP calls, section area/centroid, source edit/undo, curved/vertex/empty/stale rejection"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
