"""Actual read-only MCP measurements on a saved pair of linked planar parts."""

import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from store import ROOT

EXAMPLE = ROOT / "examples/ai-cad/measurements"


async def main(write=False):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "part.json"
        path.write_bytes(
            (
                ROOT / "examples/ai-cad/linked-instances/browser-moved.cad.json"
            ).read_bytes()
        )
        before = path.read_bytes()
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("mcp_server.py")), "--store", str(path)],
        )
        calls = []
        async with stdio_client(params) as (read, output):
            async with ClientSession(read, output) as session:
                await session.initialize()
                for revision, feature in [
                    (4, "instance1"),
                    (4, "l"),
                    (3, "instance1"),
                    (4, "absent"),
                ]:
                    args = dict(expected_revision=revision, feature_id=feature)
                    raw = await session.call_tool("cad_measure", args)
                    value = json.loads(
                        next(c.text for c in raw.content if c.type == "text")
                    )
                    if revision == 3:
                        assert value["error"]["code"] == "revision_conflict"
                    elif feature == "absent":
                        assert value["error"]["code"] == "missing_body"
                    else:
                        assert value["result"]["volume_mm3"] == "306"
                        assert value["result"]["centroid_mm"] == (
                            ["1141/34", "121/34", "3"]
                            if feature == "instance1"
                            else ["121/34", "121/34", "3"]
                        )
                    assert path.read_bytes() == before
                    calls.append(dict(tool="cad_measure", arguments=args, reply=value))
        if write:
            EXAMPLE.mkdir(parents=True, exist_ok=True)
            (EXAMPLE / "input.cad.json").write_bytes(before)
            (EXAMPLE / "mcp-recording.json").write_text(
                json.dumps(dict(calls=calls), indent=2) + "\n"
            )
    print(
        "PASS: four actual read-only MCP calls, independent linked-part centroids, stale revision and missing body rejection"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
