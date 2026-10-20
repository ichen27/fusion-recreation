"""Actual typed material assignment, inheritance, uniform override and history."""

import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from store import ROOT
from test_materials import model, assign
from test_intersection import operations

EXAMPLE = ROOT / "examples/ai-cad/materials"


async def main(write=False):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.cad.json"
        files, calls = {}, []
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("mcp_server.py")), "--store", str(path)],
        )
        async with stdio_client(params) as (read, output):
            async with ClientSession(read, output) as session:
                await session.initialize()

                async def call(tool, args):
                    raw = await session.call_tool(tool, args)
                    reply = json.loads(
                        next(c.text for c in raw.content if c.type == "text")
                    )
                    calls.append(dict(tool=tool, arguments=args, reply=reply))
                    assert "error" not in reply
                    return reply["result"]

                source = await call(
                    "cad_commit",
                    dict(
                        expected_revision=0,
                        transaction_id="create",
                        operations=operations(model()) + [assign("part")],
                        preserve=[],
                    ),
                )
                files["source.cad.json"] = path.read_bytes()
                mass = await call(
                    "cad_material_mass",
                    dict(expected_revision=1, feature_ids=["part", "copy"]),
                )
                assert mass["mass_kg"] == "1/6250"
                preview = dict(
                    expected_revision=1,
                    operations=[assign("copy", "Other material", "2000")],
                    preserve=[],
                )
                await call("cad_preview", preview)
                assert path.read_bytes() == files["source.cad.json"]
                override = await call(
                    "cad_commit", {**preview, "transaction_id": "override-copy"}
                )
                assert override["bodies"] == source["bodies"]
                files["override.cad.json"] = path.read_bytes()
                mass = await call(
                    "cad_material_mass",
                    dict(expected_revision=2, feature_ids=["part", "copy"]),
                )
                assert mass["mass_kg"] == "3/12500"
                edited = await call(
                    "cad_commit",
                    dict(
                        expected_revision=2,
                        transaction_id="source-density",
                        operations=[assign("part", density="3000")],
                        preserve=[],
                    ),
                )
                assert edited["bodies"] == source["bodies"]
                files["edited.cad.json"] = path.read_bytes()
                mass = await call(
                    "cad_material_mass",
                    dict(expected_revision=3, feature_ids=["part", "copy"]),
                )
                assert mass["mass_kg"] == "1/2500"
                await call(
                    "cad_commit",
                    dict(
                        expected_revision=3,
                        transaction_id="clear-copy",
                        operations=[dict(op="clear_material", feature_id="copy")],
                        preserve=[],
                    ),
                )
                files["inherited.cad.json"] = path.read_bytes()
                mass = await call(
                    "cad_material_mass",
                    dict(expected_revision=4, feature_ids=["part", "copy"]),
                )
                assert mass["mass_kg"] == "3/6250"
                undone = await call(
                    "cad_history",
                    dict(action="undo", expected_revision=4, transaction_id="undo"),
                )
                assert undone["model"] == edited["model"]
                files["undo.cad.json"] = path.read_bytes()
                mass = await call(
                    "cad_material_mass",
                    dict(expected_revision=5, feature_ids=["part", "copy"]),
                )
                assert mass["mass_kg"] == "1/2500"
                assert mass["material_sources"]["copy"]["source_features"] == ["copy"]
        if write:
            EXAMPLE.mkdir(parents=True, exist_ok=True)
            for name, data in files.items():
                (EXAMPLE / name).write_bytes(data)
            (EXAMPLE / "mcp-recording.json").write_text(
                json.dumps(dict(calls=calls), indent=2) + "\n"
            )
    print(
        f"PASS: {len(calls)} actual MCP calls, saved source/copy materials, exact mass, source edit, clear/inherit and undo; geometry unchanged"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
