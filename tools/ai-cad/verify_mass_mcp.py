"""Read-only uniform-density measurements through an actual stdio MCP session."""

import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from store import ROOT, Store
from measurements import dispatch_measure
from test_intersection import rectangle, operations

EXAMPLE = ROOT / "examples/ai-cad/mass"


def source(path):
    model = rectangle("box", 0, 0, 10, 4, 2)
    store = Store(path)
    store.execute(
        dict(
            action="commit",
            expected_revision=0,
            transaction_id="create",
            operations=operations(model),
            preserve=[],
        )
    )
    return model["features"][-1]["id"]


async def main(write=False):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.cad.json"
        feature_id = source(path)
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
                    t.input_schema for t in tools.tools if t.name == "cad_measure"
                )
                assert "density_kg_per_m3" in schema["properties"]
                assert "density_kg_per_m3" not in schema.get("required", [])
                for density in [None, "1000", "2000", "3/7", "0", "-1", "0.5", "1/0"]:
                    arguments = dict(expected_revision=1, feature_id=feature_id)
                    if density is not None:
                        arguments["density_kg_per_m3"] = density
                    raw = await session.call_tool("cad_measure", arguments)
                    reply = json.loads(
                        next(c.text for c in raw.content if c.type == "text")
                    )
                    assert reply == dispatch_measure(Store(path), arguments)
                    calls.append(
                        dict(tool="cad_measure", arguments=arguments, reply=reply)
                    )
                    assert path.read_bytes() == before
                arguments = dict(
                    expected_revision=0, feature_id=feature_id, density_kg_per_m3="1000"
                )
                raw = await session.call_tool("cad_measure", arguments)
                reply = json.loads(
                    next(c.text for c in raw.content if c.type == "text")
                )
                assert reply["error"]["code"] == "revision_conflict"
                calls.append(dict(tool="cad_measure", arguments=arguments, reply=reply))
        assert "mass_properties" not in calls[0]["reply"]["result"]
        assert calls[1]["reply"]["result"]["mass_properties"]["mass_kg"] == "1/12500"
        assert calls[2]["reply"]["result"]["mass_properties"]["mass_kg"] == "1/6250"
        assert [c["reply"]["error"]["code"] for c in calls[4:8]] == [
            "invalid_density",
            "invalid_density",
            "invalid_number",
            "invalid_number",
        ]
        assert path.read_bytes() == before
        if write:
            EXAMPLE.mkdir(parents=True, exist_ok=True)
            (EXAMPLE / "source.cad.json").write_bytes(before)
            (EXAMPLE / "mcp-recording.json").write_text(
                json.dumps(dict(calls=calls), indent=2) + "\n"
            )
    print(
        f"PASS: {len(calls)} actual MCP reads, optional density schema, independent box mass, invalid input, stale revision and unchanged native bytes"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
