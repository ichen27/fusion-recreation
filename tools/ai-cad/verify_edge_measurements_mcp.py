"""Exercise actual typed MCP edge reads, invalid references and stale revisions."""

import argparse
import asyncio
import copy
import json
from pathlib import Path
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from store import ROOT
from test_frustum import frustum
from test_intersection import operations

EXAMPLE = ROOT / "examples/ai-cad/edge-measurements"


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
                schema = next(
                    t.input_schema
                    for t in (await session.list_tools()).tools
                    if t.name == "cad_measure_edge"
                )
                assert schema["properties"]["edge_index"]["minimum"] == 0

                async def call(name, args):
                    raw = await session.call_tool(name, args)
                    text = next(c.text for c in raw.content if c.type == "text")
                    reply = (
                        {"validation_error": text} if raw.is_error else json.loads(text)
                    )
                    calls.append(
                        dict(tool=name, arguments=copy.deepcopy(args), reply=reply)
                    )
                    return reply

                assert "result" in await call(
                    "cad_commit",
                    dict(
                        expected_revision=0,
                        transaction_id="create",
                        operations=operations(frustum("10", "7", "4")),
                        preserve=[],
                    ),
                )
                original = path.read_bytes()
                base = dict(expected_revision=1, feature_id="taper")
                topology = (await call("cad_topology", base))["result"]
                line = next(
                    i
                    for i, e in enumerate(topology["edges"])
                    if e["curve"]["kind"] == "line"
                )
                arc = next(
                    i
                    for i, e in enumerate(topology["edges"])
                    if e["curve"]["kind"] == "quarter_circle"
                )
                measured = (
                    await call("cad_measure_edge", {**base, "edge_index": line})
                )["result"]
                assert measured["length_mm"] == "5" and measured["patch_seam"]
                measured = (
                    await call("cad_measure_edge", {**base, "edge_index": arc})
                )["result"]
                assert (
                    measured["length_mm"] == "5*pi"
                    and measured["chord_mm"] == "sqrt(200)"
                    and not measured["patch_seam"]
                )
                bad = await call(
                    "cad_measure_edge", {**base, "edge_index": len(topology["edges"])}
                )
                assert bad["error"]["code"] == "missing_edge"
                for index in (-1, True, "0"):
                    bad = await call("cad_measure_edge", {**base, "edge_index": index})
                    assert "validation_error" in bad
                assert path.read_bytes() == original
                assert "result" in await call(
                    "cad_commit",
                    dict(
                        expected_revision=1,
                        transaction_id="taller",
                        operations=[dict(op="set_parameter", id="height", mm="5")],
                        preserve=[],
                    ),
                )
                changed = path.read_bytes()
                stale = await call("cad_measure_edge", {**base, "edge_index": line})
                assert stale["error"]["code"] == "revision_conflict"
                current = (
                    await call("cad_topology", {**base, "expected_revision": 2})
                )["result"]
                line = next(
                    i
                    for i, e in enumerate(current["edges"])
                    if e["curve"]["kind"] == "line"
                )
                measured = await call(
                    "cad_measure_edge",
                    {**base, "expected_revision": 2, "edge_index": line},
                )
                assert (
                    measured["result"]["length_mm"] == "sqrt(34)"
                    and path.read_bytes() == changed
                )
        if write:
            EXAMPLE.mkdir(parents=True, exist_ok=True)
            (EXAMPLE / "source.cad.json").write_bytes(original)
            (EXAMPLE / "taller.cad.json").write_bytes(changed)
            (EXAMPLE / "mcp-recording.json").write_text(
                json.dumps(dict(calls=calls), indent=2) + "\n"
            )
    print(
        f"PASS: {len(calls)} actual MCP calls, exact arc/seam lengths, strict indices, stale rejection and unchanged native reads"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
