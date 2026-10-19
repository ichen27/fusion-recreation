"""Actual MCP surface context, shared drivers and revision invalidation."""

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
from test_counterbores import counterbored
from test_instances import instance
from test_intersection import operations

EXAMPLE = ROOT / "examples/ai-cad/surface-context"


async def main(write=False):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        model = instance(counterbored(), offset=(130, 0, 0))
        Store(path).execute(
            dict(
                action="commit",
                expected_revision=0,
                transaction_id="seed",
                operations=operations(model),
                preserve=[],
            )
        )
        initial = path.read_bytes()
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("mcp_server.py")), "--store", str(path)],
        )
        calls = []
        async with stdio_client(params) as (read, output):
            async with ClientSession(read, output) as session:
                await session.initialize()

                async def call(name, args):
                    raw = await session.call_tool(name, args)
                    value = json.loads(
                        next(c.text for c in raw.content if c.type == "text")
                    )
                    calls.append(
                        dict(tool=name, arguments=copy.deepcopy(args), reply=value)
                    )
                    return value

                schema = next(
                    t
                    for t in (await session.list_tools()).tools
                    if t.name == "cad_select_surface"
                )
                assert set(schema.input_schema["required"]) == {
                    "expected_revision",
                    "feature_id",
                    "surface_id",
                }
                topology = await call(
                    "cad_topology", dict(expected_revision=1, feature_id="copy")
                )
                reference = "feature/part/hole/left/upper"
                assert reference in topology["result"]["surfaces"]
                selected = await call(
                    "cad_select_surface",
                    dict(expected_revision=1, feature_id="copy", surface_id=reference),
                )
                context = await call("cad_context", {})
                assert context == selected
                surface = context["result"]["selected_surface"]
                assert surface["support"]["origin"] == ["142", "12", "0"]
                assert surface["source_feature"]["id"] == "part"
                explanation = await call(
                    "cad_explain",
                    dict(
                        expected_revision=1,
                        feature_id=surface["support"]["owner_feature"],
                    ),
                )
                assert set(
                    explanation["result"]["parameters"]["recess_radius"][
                        "affected_bodies"
                    ]
                ) == {"part", "copy"}
                assert path.read_bytes() == initial
                edit = dict(
                    expected_revision=1,
                    operations=[dict(op="set_parameter", id="recess_radius", mm="6")],
                    preserve=[],
                )
                assert "result" in await call("cad_preview", edit)
                assert path.read_bytes() == initial
                assert "result" in await call(
                    "cad_commit", {**edit, "transaction_id": "larger"}
                )
                edited = path.read_bytes()
                stale = await call("cad_context", {})
                assert (
                    stale["result"]["selection_status"] == "stale"
                    and stale["result"]["selected_surface"] is None
                )
                reject = await call(
                    "cad_select_surface",
                    dict(expected_revision=1, feature_id="copy", surface_id=reference),
                )
                assert reject["error"]["code"] == "revision_conflict"
                refreshed = await call(
                    "cad_select_surface",
                    dict(expected_revision=2, feature_id="copy", surface_id=reference),
                )
                assert (
                    refreshed["result"]["selected_surface"]["support"]["radius"] == "6"
                )
                reject = await call(
                    "cad_select_surface",
                    dict(
                        expected_revision=2,
                        feature_id="copy",
                        surface_id="feature/part/hole/missing/upper",
                    ),
                )
                assert reject["error"]["code"] == "missing_surface"
                assert path.read_bytes() == edited
        if write:
            EXAMPLE.mkdir(parents=True, exist_ok=True)
            (EXAMPLE / "input.cad.json").write_bytes(initial)
            (EXAMPLE / "mcp-larger.cad.json").write_bytes(edited)
            (EXAMPLE / "mcp-recording.json").write_text(
                json.dumps(dict(calls=calls), indent=2) + "\n"
            )
    print(
        "PASS: ten actual MCP calls; surface context, linked-copy impact, native edit and stale/missing rejection"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
