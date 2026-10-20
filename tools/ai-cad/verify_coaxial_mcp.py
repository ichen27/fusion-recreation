"""Actual typed MCP coaxial intersection, surface context, edit and undo."""

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
from test_coaxial import intersect
from test_intersection import operations

EXAMPLE = ROOT / "examples/ai-cad/coaxial-intersection"


async def main(write=False):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        calls = []
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("mcp_server.py")), "--store", str(path)],
        )
        async with stdio_client(params) as (read, output):
            async with ClientSession(read, output) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert "coaxial_intersection" in json.dumps(
                    next(t.input_schema for t in tools.tools if t.name == "cad_preview")
                )

                async def call(name, args):
                    raw = await session.call_tool(name, args)
                    reply = json.loads(
                        next(c.text for c in raw.content if c.type == "text")
                    )
                    calls.append(
                        dict(tool=name, arguments=copy.deepcopy(args), reply=reply)
                    )
                    return reply

                create = dict(
                    expected_revision=0,
                    operations=operations(intersect()),
                    preserve=[],
                )
                assert "result" in await call("cad_preview", create)
                assert not path.exists()
                made = await call("cad_commit", {**create, "transaction_id": "create"})
                assert made["result"]["bodies"][0]["volume_mm3"] == "150*pi"
                original = path.read_bytes()
                assert "result" in await call(
                    "cad_measure", dict(expected_revision=1, feature_id="common")
                )
                assert path.read_bytes() == original
                topology = await call(
                    "cad_topology", dict(expected_revision=1, feature_id="common")
                )
                surface = next(iter(topology["result"]["surfaces"]))
                assert "result" in await call(
                    "cad_select_surface",
                    dict(
                        expected_revision=1,
                        feature_id="common",
                        surface_id=surface,
                    ),
                )
                edit = dict(
                    expected_revision=1,
                    selection_guard=dict(feature_id="common", surface_id=surface),
                    operations=[dict(op="set_parameter", id="right.radius", mm="6")],
                    preserve=[],
                )
                assert "result" in await call("cad_preview", edit)
                assert path.read_bytes() == original
                assert "result" in await call(
                    "cad_commit", {**edit, "transaction_id": "deeper"}
                )
                deeper = path.read_bytes()
                bad = await call(
                    "cad_preview",
                    dict(
                        expected_revision=2,
                        operations=[
                            dict(op="set_parameter", id="right.move.z", mm="20")
                        ],
                        preserve=[],
                    ),
                )
                assert (
                    bad["error"]["code"] == "empty_solid"
                    and path.read_bytes() == deeper
                )
                undone = await call(
                    "cad_history",
                    dict(action="undo", expected_revision=2, transaction_id="undo"),
                )
                assert undone["result"]["bodies"][0]["volume_mm3"] == "150*pi"
                assert "result" in await call(
                    "cad_measure", dict(expected_revision=3, feature_id="common")
                )
                assert Store(path).execute(dict(action="inspect"))["revision"] == 3
        if write:
            EXAMPLE.mkdir(parents=True, exist_ok=True)
            for name, data in [
                ("mcp-created.cad.json", original),
                ("mcp-edited.cad.json", deeper),
                ("mcp-undo.cad.json", path.read_bytes()),
            ]:
                (EXAMPLE / name).write_bytes(data)
            (EXAMPLE / "mcp-recording.json").write_text(
                json.dumps(dict(calls=calls), indent=2) + "\n"
            )
    print(
        "PASS: ten actual typed MCP calls, exact coaxial intersection, surface context/edit/rejection/undo"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
