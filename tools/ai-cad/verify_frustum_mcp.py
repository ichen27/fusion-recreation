"""Actual typed MCP tapered-stock creation, topology, measurement and guarded editing."""

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
from test_frustum import frustum
from test_intersection import operations

EXAMPLE = ROOT / "examples/ai-cad/tapered-stock"


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
                assert "conical_frustum" in json.dumps(
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
                    operations=operations(frustum()),
                    preserve=[],
                )
                assert "result" in await call("cad_preview", create)
                assert not path.exists()
                made = await call("cad_commit", {**create, "transaction_id": "create"})
                assert made["result"]["bodies"][0]["volume_mm3"] == "700*pi"
                original = path.read_bytes()
                assert "result" in await call(
                    "cad_measure", dict(expected_revision=1, feature_id="taper")
                )
                assert path.read_bytes() == original
                topology = await call(
                    "cad_topology", dict(expected_revision=1, feature_id="taper")
                )
                assert "conical_frustum" in json.dumps(topology)
                selected = await call(
                    "cad_select_surface",
                    dict(
                        expected_revision=1,
                        feature_id="taper",
                        surface_id="feature/taper/outer/frustum",
                    ),
                )
                assert "result" in selected
                assert path.read_bytes() == original
                edit = dict(
                    expected_revision=1,
                    selection_guard=dict(
                        feature_id="taper", surface_id="feature/taper/outer/frustum"
                    ),
                    operations=[dict(op="set_parameter", id="top", mm="15")],
                    preserve=[],
                )
                assert "result" in await call("cad_preview", edit)
                assert path.read_bytes() == original
                assert "result" in await call(
                    "cad_commit", {**edit, "transaction_id": "wider"}
                )
                wider = path.read_bytes()
                bad = await call(
                    "cad_preview",
                    dict(
                        expected_revision=2,
                        operations=[dict(op="set_parameter", id="top", mm="10")],
                        preserve=[],
                    ),
                )
                assert (
                    bad["error"]["code"] == "invalid_taper"
                    and path.read_bytes() == wider
                )
                undone = await call(
                    "cad_history",
                    dict(action="undo", expected_revision=2, transaction_id="undo"),
                )
                assert undone["result"]["bodies"][0]["volume_mm3"] == "700*pi"
                assert "result" in await call(
                    "cad_measure", dict(expected_revision=3, feature_id="taper")
                )
                assert Store(path).execute(dict(action="inspect"))["revision"] == 3
        if write:
            EXAMPLE.mkdir(parents=True, exist_ok=True)
            for name, data in [
                ("mcp-created.cad.json", original),
                ("mcp-wider.cad.json", wider),
                ("mcp-undo.cad.json", path.read_bytes()),
            ]:
                (EXAMPLE / name).write_bytes(data)
            (EXAMPLE / "mcp-recording.json").write_text(
                json.dumps(dict(calls=calls), indent=2) + "\n"
            )
    print(
        "PASS: ten actual typed MCP calls, tapered stock, conical surface context, guarded edit/rejection/undo"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
