"""Actual typed MCP combined-mass reads against an isolated editable document."""

import argparse
import asyncio
from fractions import Fraction as F
import json
from pathlib import Path
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from store import ROOT, Store
from mass_properties import dispatch_mass_set
from test_mass_set import source, parts
from test_intersection import operations

EXAMPLE = ROOT / "examples/ai-cad/combined-mass"


async def main(write=False):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.cad.json"
        Store(path).execute(
            dict(
                action="commit",
                expected_revision=0,
                transaction_id="create",
                operations=operations(source()),
                preserve=[],
            )
        )
        before = path.read_bytes()
        calls = []
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("mcp_server.py")), "--store", str(path)],
        )
        async with stdio_client(params) as (read, output):
            async with ClientSession(read, output) as session:
                await session.initialize()
                tools = await session.list_tools()
                schema = next(
                    t.input_schema
                    for t in tools.tools
                    if t.name == "cad_mass_properties"
                )
                assert "parts" in schema["properties"]
                cases = [
                    (1, parts()),
                    (1, parts()[::-1]),
                    (1, parts("2000", "4000")),
                    (1, [parts()[0]]),
                    (1, parts("0")),
                    (1, [parts()[0]] * 2),
                    (0, parts()),
                ]
                for revision, selected in cases:
                    arguments = dict(expected_revision=revision, parts=selected)
                    raw = await session.call_tool("cad_mass_properties", arguments)
                    reply = json.loads(
                        next(c.text for c in raw.content if c.type == "text")
                    )
                    assert reply == dispatch_mass_set(Store(path), arguments)
                    calls.append(
                        dict(
                            tool="cad_mass_properties", arguments=arguments, reply=reply
                        )
                    )
                    assert path.read_bytes() == before
        assert calls[0]["reply"] == calls[1]["reply"]
        first = calls[0]["reply"]["result"]
        assert first["mass_kg"] == "3/12500"
        assert first["center_of_mass_mm"] == ["55/3", "22", "83/3"]
        assert F(calls[2]["reply"]["result"]["mass_kg"]) == 2 * F(first["mass_kg"])
        assert [c["reply"]["error"]["code"] for c in calls[4:]] == [
            "invalid_density",
            "duplicate_id",
            "revision_conflict",
        ]
        if write:
            EXAMPLE.mkdir(parents=True, exist_ok=True)
            (EXAMPLE / "source.cad.json").write_bytes(before)
            (EXAMPLE / "mcp-recording.json").write_text(
                json.dumps(dict(calls=calls), indent=2) + "\n"
            )
    print(
        f"PASS: {len(calls)} actual typed MCP calls, mixed density, canonical order, invalid/stale selection and unchanged native bytes"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
