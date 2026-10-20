"""Actual typed coupled-constraint creation, driver edits, diagnostics and history."""

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
from test_linear_constraints import source_operations, dimensions, constrain, equation

EXAMPLE = ROOT / "examples/ai-cad/linear-constraints"


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
                tools = await session.list_tools()
                assert "constrain_linear" in json.dumps(
                    next(t.input_schema for t in tools.tools if t.name == "cad_preview")
                )

                async def call(name, arguments):
                    raw = await session.call_tool(name, arguments)
                    reply = json.loads(
                        next(c.text for c in raw.content if c.type == "text")
                    )
                    calls.append(
                        dict(tool=name, arguments=copy.deepcopy(arguments), reply=reply)
                    )
                    return reply

                creation = dict(
                    expected_revision=0,
                    operations=source_operations() + [dimensions()],
                    preserve=[],
                )
                preview = await call("cad_preview", creation)
                assert preview["result"]["model"]["relations"]["left"]["terms"] == {
                    "gap": "-2/3",
                    "span": "2/3",
                }
                assert not path.exists()
                created = await call(
                    "cad_commit", {**creation, "transaction_id": "create"}
                )
                assert [b["volume_mm3"] for b in created["result"]["bodies"]] == [
                    "12000",
                    "6000",
                ]
                snapshots["created"] = path.read_bytes()
                explained = await call(
                    "cad_explain", dict(expected_revision=1, feature_id="right_placed")
                )
                assert explained["result"]["parameters"]["offset"][
                    "driving_parameters"
                ] == ["gap", "span"]
                assert not explained["result"]["parameters"]["offset"][
                    "directly_editable"
                ]
                edit = dict(
                    expected_revision=1,
                    operations=[dict(op="set_parameter", id="span", mm="130")],
                    preserve=["gap", "depth", "height"],
                )
                preview = await call("cad_preview", edit)
                assert [b["volume_mm3"] for b in preview["result"]["bodies"]] == [
                    "16000",
                    "8000",
                ]
                assert path.read_bytes() == snapshots["created"]
                assert "result" in await call(
                    "cad_commit", {**edit, "transaction_id": "widen"}
                )
                snapshots["edited"] = path.read_bytes()
                placement = await call(
                    "cad_measure", dict(expected_revision=2, feature_id="right_placed")
                )
                assert placement["result"]["centroid_mm"] == ["110", "5", "10"]
                # Both compile failure and attempts to override a solved dimension
                # must leave the current valid rules and file untouched.
                bad = constrain(
                    ["left", "right"], [equation("sum", dict(left=1, right=1))]
                )
                rejected = await call(
                    "cad_preview",
                    dict(expected_revision=2, operations=[bad], preserve=[]),
                )
                assert rejected["error"]["code"] == "linear_underdetermined"
                direct = await call(
                    "cad_preview",
                    dict(
                        expected_revision=2,
                        operations=[dict(op="set_parameter", id="left", mm="90")],
                        preserve=[],
                    ),
                )
                assert direct["error"]["code"] == "derived_parameter"
                assert path.read_bytes() == snapshots["edited"]
                undone = await call(
                    "cad_history",
                    dict(action="undo", expected_revision=2, transaction_id="undo"),
                )
                assert undone["result"]["model"]["parameters"]["right"] == "30"
                snapshots["undo"] = path.read_bytes()
                measured = await call(
                    "cad_measure", dict(expected_revision=3, feature_id="right_placed")
                )
                assert "result" in measured
                assert (
                    Store(path).execute(dict(action="inspect"))["model"]["relations"]
                    == created["result"]["model"]["relations"]
                )
        if write:
            EXAMPLE.mkdir(parents=True, exist_ok=True)
            for name, data in snapshots.items():
                (EXAMPLE / f"mcp-{name}.cad.json").write_bytes(data)
            (EXAMPLE / "mcp-recording.json").write_text(
                json.dumps(dict(calls=calls), indent=2) + "\n"
            )
            (EXAMPLE / "create.request.json").write_text(
                json.dumps(creation, indent=2) + "\n"
            )
    print(
        f"PASS: {len(calls)} actual typed MCP calls, coupled symbolic rules, driver edits, rank/derived-parameter diagnostics and undo"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
