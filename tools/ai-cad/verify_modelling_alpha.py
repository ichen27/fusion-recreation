"""Exercise three editable alpha parts through real MCP, native reopen and exports."""

import argparse
import asyncio
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from store import ROOT, Store
from exports import export_stl
from drawings import dispatch_drawing
from test_holes import read_stl, audit_triangles
from test_counterbores import counterbored
from test_intersection import operations
from test_references import surface, rim, SHOULDER
from test_revolution import revolved

EXAMPLE = ROOT / "examples/ai-cad/modelling-alpha"


def scenarios():
    # Use the same authoring code as the browser, then validate in the Rust engine.
    script = """
      import {draftSketch,startRectangle,sketchOperations} from './tools/ai-cad/web/sketch-model.mjs';
      const d=draftSketch({parameters:{},features:[],fixed:{}},'plate');
      startRectangle(d,'100','60');d.height='6';
      console.log(JSON.stringify(sketchOperations(d)));
    """
    rectangle = json.loads(
        subprocess.check_output(
            ["node", "--input-type=module", "-e", script], cwd=ROOT, text=True
        )
    )
    rectangle.append(dict(op="fix_parameter", id="plate.height"))
    return [
        dict(
            name="rectangular-plate",
            feature="plate.solid",
            operations=rectangle,
            edit=[dict(op="set_parameter", id="plate.width", mm="120")],
            preserve=["plate.depth", "plate.height"],
            volumes=["36000", "43200"],
            genus=0,
            bad=[dict(op="set_parameter", id="plate.height", mm="9")],
            bad_code="constraint_conflict",
        ),
        dict(
            name="counterbored-mount",
            feature="part",
            operations=operations(counterbored()) + [surface(), rim()],
            edit=[dict(op="set_parameter", id="recess_depth", mm="3")],
            preserve=["height", "recess_radius"],
            volumes=["36000 - (172)*pi", "36000 - (204)*pi"],
            genus=2,
            bad=[dict(op="set_parameter", id="recess_radius", mm="12")],
            bad_code="hole_clearance",
        ),
        dict(
            name="turned-spacer",
            feature="revolved",
            operations=operations(revolved([(3, 0), (10, 0), (10, 12), (3, 12)])),
            edit=[dict(op="set_parameter", id="c3", mm="15")],
            preserve=["c0", "c2"],
            volumes=["1092*pi", "1365*pi"],
            genus=1,
            bad=[dict(op="set_parameter", id="c3", mm="0")],
            bad_code="invalid_profile",
        ),
    ]


async def verify(write=False):
    reports = []
    for case in scenarios():
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.cad.json"
            params = StdioServerParameters(
                command=sys.executable,
                args=[
                    str(Path(__file__).with_name("mcp_server.py")),
                    "--store",
                    str(path),
                ],
            )
            calls, files = [], {}
            async with stdio_client(params) as (read, output):
                async with ClientSession(read, output) as client:
                    await client.initialize()
                    schema = await client.list_tools()
                    assert "set_reference" in json.dumps(
                        next(
                            t.input_schema
                            for t in schema.tools
                            if t.name == "cad_preview"
                        )
                    )

                    async def call(tool, args, code=None):
                        raw = await client.call_tool(tool, args)
                        reply = json.loads(
                            next(c.text for c in raw.content if c.type == "text")
                        )
                        calls.append(
                            dict(tool=tool, arguments=copy.deepcopy(args), reply=reply)
                        )
                        if code:
                            assert reply.get("error", {}).get("code") == code, reply
                            return reply
                        assert "result" in reply, reply
                        return reply["result"]

                    create = dict(
                        expected_revision=0, operations=case["operations"], preserve=[]
                    )
                    await call("cad_preview", create)
                    assert not path.exists()
                    source = await call(
                        "cad_commit", {**create, "transaction_id": "create"}
                    )
                    assert source["bodies"][0]["volume_mm3"] == case["volumes"][0], (
                        source["bodies"][0]["volume_mm3"]
                    )
                    files["source.cad.json"] = path.read_bytes()
                    edit = dict(
                        expected_revision=1,
                        operations=case["edit"],
                        preserve=case["preserve"],
                    )
                    await call("cad_preview", edit)
                    assert path.read_bytes() == files["source.cad.json"]
                    edited = await call(
                        "cad_commit", {**edit, "transaction_id": "resize"}
                    )
                    assert edited["bodies"][0]["volume_mm3"] == case["volumes"][1]
                    files["edited.cad.json"] = path.read_bytes()
                    assert (
                        Store(path).execute(dict(action="inspect"))["model"]
                        == edited["model"]
                    )
                    for request, code in [
                        (
                            dict(
                                expected_revision=2, operations=case["bad"], preserve=[]
                            ),
                            case["bad_code"],
                        ),
                        (edit, "revision_conflict"),
                    ]:
                        await call("cad_preview", request, code)
                        assert path.read_bytes() == files["edited.cad.json"]
                    if case["name"] == "counterbored-mount":
                        assert (
                            len(edited["resolved_references"]["rim"]["edge_indices"])
                            == 4
                        )
                        topology = await call(
                            "cad_topology", dict(expected_revision=2, feature_id="part")
                        )
                        assert topology["surfaces"][SHOULDER]["offset"] == "3"
                        replacement = copy.deepcopy(edited["model"]["features"][-1])
                        replacement["holes"].reverse()
                        await call(
                            "cad_preview",
                            dict(
                                expected_revision=2,
                                operations=[
                                    dict(
                                        op="replace_feature",
                                        id="part",
                                        feature=replacement,
                                    )
                                ],
                                preserve=[],
                            ),
                            "reference_changed",
                        )
                        assert path.read_bytes() == files["edited.cad.json"]
                    # Exports must be read-only, reopenable and geometrically closed.
                    data, mesh = export_stl(Store(path), 2, case["feature"], 128)
                    volume = audit_triangles(read_stl(data), case["genus"])
                    assert volume > 0
                    files["edited.stl"] = data
                    drawing = dispatch_drawing(
                        Store(path),
                        dict(
                            expected_revision=2,
                            feature_id=case["feature"],
                            style="all_edges",
                        ),
                    )
                    assert "result" in drawing, drawing
                    files["edited.svg"] = drawing["result"]["svg"].encode()
                    assert path.read_bytes() == files["edited.cad.json"]
                    undo = await call(
                        "cad_history",
                        dict(action="undo", expected_revision=2, transaction_id="undo"),
                    )
                    assert undo["model"] == source["model"]
                    redo = await call(
                        "cad_history",
                        dict(action="redo", expected_revision=3, transaction_id="redo"),
                    )
                    assert redo["model"] == edited["model"]
                    files["reopened.cad.json"] = path.read_bytes()
                    assert (await call("cad_inspect", {}))["model"] == edited["model"]
            report = dict(
                part=case["name"],
                calls=len(calls),
                initial_volume_mm3=case["volumes"][0],
                edited_volume_mm3=case["volumes"][1],
                triangles=len(mesh["triangles"]),
                mesh_volume_mm3=volume,
                native_reopen=True,
                preview_readonly=True,
                stale_and_invalid_edits_rejected=True,
                undo_redo=True,
                stl_closed=True,
                reference_sheet=True,
            )
            reports.append(report)
            if write:
                folder = EXAMPLE / case["name"]
                folder.mkdir(parents=True, exist_ok=True)
                for name, data in files.items():
                    (folder / name).write_bytes(data)
                (folder / "mcp-recording.json").write_text(
                    json.dumps(dict(calls=calls), indent=2) + "\n"
                )
    if write:
        (EXAMPLE / "verification.json").write_text(json.dumps(reports, indent=2) + "\n")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    asyncio.run(verify(parser.parse_args().write))
