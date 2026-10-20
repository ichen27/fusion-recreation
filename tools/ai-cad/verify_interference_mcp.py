"""Actual typed MCP interference reads across creation, placement edits and undo."""

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
from test_interference import examples
from test_intersection import operations
from test_frustum import frustum

EXAMPLE = ROOT / "examples/ai-cad/interference"


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
                assert "cad_interference" in {
                    t.name for t in (await session.list_tools()).tools
                }

                async def call(name, args):
                    raw = await session.call_tool(name, args)
                    reply = json.loads(
                        next(c.text for c in raw.content if c.type == "text")
                    )
                    calls.append(
                        dict(tool=name, arguments=copy.deepcopy(args), reply=reply)
                    )
                    return reply

                model, left, right, _ = examples()["overlap"]
                assert "result" in await call(
                    "cad_commit",
                    dict(
                        expected_revision=0,
                        transaction_id="create",
                        operations=operations(model),
                        preserve=[],
                    ),
                )
                original = path.read_bytes()
                base = dict(expected_revision=1, left=left, right=right)
                result = await call("cad_interference", base)
                assert result["result"]["overlap_volume_mm3"] == "40"
                assert (await call("cad_interference", {**base, "right": left}))[
                    "error"
                ]["code"] == "invalid_pair"
                assert path.read_bytes() == original
                edit = dict(
                    expected_revision=1,
                    operations=[dict(op="set_parameter", id="copy.x", mm="10")],
                    preserve=[],
                )
                assert "result" in await call("cad_preview", edit)
                assert path.read_bytes() == original
                assert "result" in await call(
                    "cad_commit", {**edit, "transaction_id": "contact"}
                )
                contact = path.read_bytes()
                assert (await call("cad_interference", base))["error"][
                    "code"
                ] == "revision_conflict"
                result = await call(
                    "cad_interference", {**base, "expected_revision": 2}
                )
                assert (
                    result["result"]["overlap_volume_mm3"] == "0"
                    and path.read_bytes() == contact
                )
                assert "result" in await call(
                    "cad_history",
                    dict(action="undo", expected_revision=2, transaction_id="undo"),
                )
                undone = path.read_bytes()
                assert (
                    await call("cad_interference", {**base, "expected_revision": 3})
                )["result"]["overlap_volume_mm3"] == "40"
                assert path.read_bytes() == undone
                assert "result" in await call(
                    "cad_commit",
                    dict(
                        expected_revision=3,
                        transaction_id="curved",
                        operations=operations(frustum()),
                        preserve=[],
                    ),
                )
                curved = path.read_bytes()
                bad = await call(
                    "cad_interference",
                    dict(expected_revision=4, left=left, right="taper"),
                )
                assert (
                    bad["error"]["code"] == "unsupported_interference"
                    and path.read_bytes() == curved
                )
        if write:
            EXAMPLE.mkdir(parents=True, exist_ok=True)
            for name, data in [
                ("source", original),
                ("contact", contact),
                ("undo", undone),
                ("curved", curved),
            ]:
                (EXAMPLE / (name + ".cad.json")).write_bytes(data)
            (EXAMPLE / "mcp-recording.json").write_text(
                json.dumps(dict(calls=calls), indent=2) + "\n"
            )
    print(
        f"PASS: {len(calls)} actual MCP calls, exact overlap, contact, stale rejection, undo and explicit curved rejection"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(main(parser.parse_args().write))
