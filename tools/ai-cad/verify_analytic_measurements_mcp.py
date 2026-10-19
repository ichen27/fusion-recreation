"""Actual MCP symbolic measurements before/after a shared blind-depth edit."""

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
from test_holes import perforated
from test_blind_holes import blind
from test_instances import instance
from test_polyhedral_transforms import turned
from test_intersection import operations
from test_analytic_measurements import exact_value

EXAMPLE = ROOT / "examples/ai-cad/analytic-measurements"


async def main(write=False):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        model = turned(instance(blind(perforated()), offset=(130, 0, 0)), "x", 1)
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

                source = await call(
                    "cad_measure", dict(expected_revision=1, feature_id="part")
                )
                placed = await call(
                    "cad_measure", dict(expected_revision=1, feature_id="turned")
                )
                assert placed["result"]["centroid_mm"][0] == "180"
                assert (
                    source["result"]["volume_mm3"]
                    == placed["result"]["volume_mm3"]
                    == "36000 - (36)*pi"
                )
                assert path.read_bytes() == initial
                edit = dict(
                    expected_revision=1,
                    operations=[dict(op="set_parameter", id="depth", mm="3")],
                    preserve=[],
                )
                assert "result" in await call("cad_preview", edit)
                assert path.read_bytes() == initial
                assert "result" in await call(
                    "cad_commit", {**edit, "transaction_id": "deeper"}
                )
                edited = path.read_bytes()
                after = await call(
                    "cad_measure", dict(expected_revision=2, feature_id="turned")
                )
                assert after["result"]["volume_mm3"] == "36000 - (54)*pi"
                assert exact_value(after["result"]["centroid_mm"][1]) != exact_value(
                    placed["result"]["centroid_mm"][1]
                )
                stale = await call(
                    "cad_measure", dict(expected_revision=1, feature_id="turned")
                )
                assert stale["error"]["code"] == "revision_conflict"
                assert path.read_bytes() == edited
        if write:
            EXAMPLE.mkdir(parents=True, exist_ok=True)
            (EXAMPLE / "input.cad.json").write_bytes(initial)
            (EXAMPLE / "mcp-deeper.cad.json").write_bytes(edited)
            (EXAMPLE / "mcp-recording.json").write_text(
                json.dumps(dict(calls=calls), indent=2) + "\n"
            )
    print(
        "PASS: six actual MCP calls, symbolic source/placed measurements, shared depth edit and stale-read rejection"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
