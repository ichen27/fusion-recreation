"""Extract and exercise a runtime away from its checkout, including optional MCP."""

import argparse
import asyncio
import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]


async def mcp_probe(root, store):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=[str(root / "cad.py"), "mcp", "--store", str(store)],
    )
    calls = []
    async with stdio_client(params) as (read, output):
        async with ClientSession(read, output) as session:
            await session.initialize()
            requests = [
                ("cad_inspect", {}),
                (
                    "cad_material_mass",
                    dict(expected_revision=1, feature_ids=["part", "copy"]),
                ),
                (
                    "cad_section",
                    dict(
                        expected_revision=1, feature_id="part", axis="Y", offset_mm="2"
                    ),
                ),
            ]
            if (root / "tools/ai-cad/inventory.py").exists():
                requests.append(("cad_inventory", dict(expected_revision=1)))
            for tool, args in requests:
                raw = await session.call_tool(tool, args)
                reply = json.loads(
                    next(c.text for c in raw.content if c.type == "text")
                )
                assert "error" not in reply
                calls.append(dict(tool=tool, arguments=args, reply=reply))
    assert len(calls[0]["reply"]["result"]["bodies"]) == 2
    assert calls[1]["reply"]["result"]["mass_kg"] == "1/6250"
    assert calls[2]["reply"]["result"]["area_mm2"] == "20"
    if len(calls) == 4:
        inventory = calls[3]["reply"]["result"]
        assert inventory["solid_count"] == 2
        assert [r["volume_mm3"] for r in inventory["rows"]] == ["80", "80"]
        assert inventory["material_counts"]["assigned"] == 2
    print(json.dumps(dict(calls=calls)))


def verify(archive, mcp_python=None, report=None):
    (ROOT / "work").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="runtime isolated ", dir=ROOT / "work"
    ) as directory:
        destination = Path(directory).resolve()
        with tarfile.open(archive, "r:gz") as bundle:
            for member in bundle.getmembers():
                target = destination / member.name
                if (
                    not member.isfile()
                    or destination not in target.resolve().parents
                    or not member.name.startswith("original-cad/")
                ):
                    raise ValueError("Archive contains an unsafe or unexpected member")
            bundle.extractall(destination, filter="data")
        root = destination / "original-cad"
        core_environment = {
            k: v
            for k, v in os.environ.items()
            if k not in ("PYTHONPATH", "CARGO_HOME", "RUSTUP_HOME")
        }
        core_environment["PATH"] = "/usr/bin:/bin"

        def launch(action, *args, input=None, check=True):
            return subprocess.run(
                [sys.executable, "-S", str(root / "cad.py"), action, *args],
                env=core_environment,
                input=input,
                text=True,
                capture_output=True,
                cwd=destination,
                timeout=30,
                check=check,
            )

        health = json.loads(launch("doctor").stdout)
        document = destination / "editable document.cad.json"
        shutil.copyfile(root / "samples/materials.cad.json", document)
        inspect = json.loads(
            launch(
                "command", "--store", str(document), input='{"action":"inspect"}'
            ).stdout
        )
        assert len(inspect["result"]["bodies"]) == 2
        internal = launch(
            "viewer", "--store", str(root / "samples/materials.cad.json"), check=False
        )
        assert internal.returncode and "outside the runtime" in internal.stderr
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        log = destination / "viewer.log"
        with log.open("wb") as stream:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-S",
                    str(root / "cad.py"),
                    "viewer",
                    "--store",
                    str(document),
                    "--port",
                    str(port),
                ],
                cwd=destination,
                env=core_environment,
                stdout=stream,
                stderr=stream,
            )

            def request(method, path, command=None):
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                try:
                    connection.request(
                        method,
                        path,
                        json.dumps(command) if command is not None else None,
                        {"Content-Type": "application/json"}
                        if command is not None
                        else {},
                    )
                    response = connection.getresponse()
                    return response.status, response.read()
                finally:
                    connection.close()

            try:
                deadline = time.monotonic() + 10
                while True:
                    try:
                        status, data = request("GET", "/api/model")
                        break
                    except OSError:
                        if process.poll() is not None or time.monotonic() > deadline:
                            raise AssertionError(log.read_text())
                        time.sleep(0.05)
                assert status == 200 and len(json.loads(data)["result"]["bodies"]) == 2
                assets = []
                for path in sorted((root / "tools/ai-cad/web").iterdir()):
                    url = "/" if path.name == "index.html" else "/" + path.name
                    status, data = request("GET", url)
                    assert status == 200 and data == path.read_bytes(), url
                    assets.append(url)
                before = document.read_bytes()
                command = dict(
                    action="preview",
                    expected_revision=1,
                    operations=[dict(op="set_parameter", id="part.height", mm="3")],
                    preserve=[],
                )
                status, data = request("POST", "/api/preview-jobs", command)
                assert status == 200
                job = json.loads(data)["result"]["job_id"]
                deadline = time.monotonic() + 15
                while True:
                    status, data = request("GET", "/api/preview-jobs?id=" + job)
                    value = json.loads(data)["result"]
                    if "reply" in value:
                        break
                    assert time.monotonic() < deadline
                    time.sleep(0.05)
                assert [
                    b["volume_mm3"] for b in value["reply"]["result"]["bodies"]
                ] == ["120", "120"]
                assert document.read_bytes() == before
                status, data = request(
                    "POST",
                    "/api/command",
                    {
                        **command,
                        "action": "commit",
                        "transaction_id": "bundle-http-edit",
                    },
                )
                assert status == 200 and json.loads(data)["result"]["revision"] == 2
                if (root / "tools/ai-cad/inventory.py").exists():
                    before = document.read_bytes()
                    status, data = request(
                        "POST", "/api/inventory", dict(expected_revision=2)
                    )
                    assert status == 200
                    inventory = json.loads(data)["result"]
                    assert [r["volume_mm3"] for r in inventory["rows"]] == [
                        "120",
                        "120",
                    ]
                    assert document.read_bytes() == before
            finally:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    raise
        optional_mcp = None
        if mcp_python:
            shutil.copyfile(root / "samples/materials.cad.json", document)
            before = document.read_bytes()
            output = subprocess.check_output(
                [
                    str(mcp_python),
                    str(Path(__file__).resolve()),
                    "--mcp-probe",
                    str(root),
                    str(document),
                ],
                text=True,
                cwd=destination,
                timeout=30,
            )
            optional_mcp = json.loads(output)
            assert document.read_bytes() == before
        manifest_path = root / "manifest.json"
        manifest_bytes = manifest_path.read_bytes()
        changed = json.loads(manifest_bytes)
        changed["platform"]["machine"] = "wrong-architecture"
        manifest_path.write_text(json.dumps(changed))
        rejected = launch("doctor", check=False)
        assert rejected.returncode and "architecture" in rejected.stderr
        manifest_path.write_bytes(manifest_bytes)
        asset = root / "tools/ai-cad/web/app.js"
        original = asset.read_bytes()
        asset.write_bytes(original + b"\nchanged\n")
        rejected = launch("doctor", check=False)
        assert rejected.returncode and "integrity mismatch" in rejected.stderr
        asset.write_bytes(original)
        binary = root / "crates/model-engine/target/release/model-engine"
        assert b"/Volumes/SamsungSSD1" not in binary.read_bytes()
        result = dict(
            archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
            archive_bytes=archive.stat().st_size,
            doctor=health,
            http_assets=assets,
            http_preview_save="passed",
            core_site_packages_disabled=True,
            core_toolchain_path_removed=True,
            external_document_policy="passed",
            platform_mismatch_rejected=True,
            tampering_rejected=True,
            development_path_remapping="passed",
            mcp=optional_mcp,
        )
        if report:
            report.write_text(json.dumps(result, indent=2) + "\n")
        print(
            f"PASS: isolated runtime doctor, CLI, {len(assets)} HTTP assets, actual preview/save, platform/tamper rejection"
            + (
                f" and{len(optional_mcp['calls'])} actual MCP calls"
                if optional_mcp
                else ""
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?")
    parser.add_argument("--mcp-python", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--mcp-probe", nargs=2, type=Path)
    args = parser.parse_args()
    if args.mcp_probe:
        asyncio.run(mcp_probe(*args.mcp_probe))
    elif args.archive:
        verify(args.archive, args.mcp_python, args.report)
    else:
        parser.error("Pass an archive")
