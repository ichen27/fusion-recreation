#!/usr/bin/env python3
"""Entry point copied to the root of a verified portable CAD runtime bundle."""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import runpy
import re
import shutil
import subprocess
import sys
import tempfile


def verify(root):
    root = root.resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    if (
        not isinstance(manifest, dict)
        or type(manifest.get("format_version")) is not int
        or manifest["format_version"] != 1
    ):
        raise ValueError("Unsupported runtime manifest version")
    required = {
        "cad.py",
        "tools/ai-cad/store.py",
        "tools/ai-cad/viewer.py",
        "tools/ai-cad/mcp_server.py",
        "crates/model-engine/target/release/model-engine",
        "samples/materials.cad.json",
    }
    if not isinstance(manifest.get("files"), dict) or not required.issubset(
        manifest["files"]
    ):
        raise ValueError("Runtime manifest is missing required files")
    if not isinstance(manifest.get("platform"), dict) or not {
        "system",
        "machine",
    }.issubset(manifest["platform"]):
        raise ValueError("Runtime manifest is missing platform information")
    if (
        not isinstance(manifest.get("source_commit"), str)
        or not re.fullmatch(r"[0-9a-f]{40}", manifest["source_commit"])
        or type(manifest.get("source_dirty")) is not bool
    ):
        raise ValueError("Runtime manifest has invalid source provenance")
    if (
        platform.system() != manifest["platform"]["system"]
        or platform.machine() != manifest["platform"]["machine"]
    ):
        raise ValueError(
            "This runtime was built for another operating system or CPU architecture"
        )
    if sys.version_info < (3, 14):
        raise ValueError("This runtime requires Python3.14 or newer")
    for name, expected in manifest["files"].items():
        if (
            not isinstance(expected, dict)
            or set(expected) != {"bytes", "sha256", "executable"}
            or type(expected["bytes"]) is not int
            or expected["bytes"] < 0
            or type(expected["executable"]) is not bool
            or not isinstance(expected["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected["sha256"])
        ):
            raise ValueError(f"Invalid runtime file record: {name}")
        path = root / name
        if (
            path.is_symlink()
            or root not in path.resolve().parents
            or not path.is_file()
        ):
            raise ValueError(f"Missing or unsafe runtime file: {name}")
        if (
            path.stat().st_size != expected["bytes"]
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]
        ):
            raise ValueError(f"Runtime file integrity mismatch: {name}")
        if expected["executable"] and not os.access(path, os.X_OK):
            raise ValueError(f"Runtime executable permission is missing: {name}")
    return manifest


def require(condition, message):
    if not condition:
        raise ValueError(message)


def mcp_environment(root):
    mismatches = []
    required_mcp = installed_mcp = None
    for line in (root / "requirements.lock").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)", line)
        if not match:
            raise ValueError("Invalid pinned MCP requirements.lock")
        package, required = match.groups()
        try:
            installed = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            installed = None
        if installed != required:
            mismatches.append(package)
        if package == "mcp":
            required_mcp, installed_mcp = required, installed
    if required_mcp is None:
        raise ValueError("MCP dependency pin is missing")
    return dict(
        ready=not mismatches,
        required_mcp=required_mcp,
        installed_mcp=installed_mcp,
        mismatched_packages=mismatches,
    )


def doctor(root, manifest):
    from store import Store
    from materials import dispatch_material_mass
    from sections import dispatch_section
    from engine_transport import WORKER

    try:
        with tempfile.TemporaryDirectory(prefix="cad-runtime-check-") as directory:
            path = Path(directory) / "scratch.cad.json"
            shutil.copyfile(root / "samples/materials.cad.json", path)
            store = Store(path)
            initial = store.load()
            baseline = store.execute(dict(action="inspect"))
            before = path.read_bytes()
            preview = store.execute(
                dict(
                    action="preview",
                    expected_revision=1,
                    operations=[dict(op="set_parameter", id="part.height", mm="3")],
                    preserve=[],
                )
            )
            require(
                [b["volume_mm3"] for b in preview["bodies"]] == ["120", "120"],
                "Preview geometry differs from expected fixture",
            )
            require(path.read_bytes() == before, "Preview altered the native document")
            store.execute(
                dict(
                    action="commit",
                    expected_revision=1,
                    transaction_id="doctor-edit",
                    operations=[dict(op="set_parameter", id="part.height", mm="3")],
                    preserve=[],
                )
            )
            Store(path).execute(
                dict(action="undo", expected_revision=2, transaction_id="doctor-undo")
            )
            require(
                Store(path).load()["model"] == initial["model"],
                "Reopen/undo did not restore the original model",
            )
            mass = dispatch_material_mass(
                store, dict(expected_revision=3, feature_ids=["part", "copy"])
            )
            require(
                mass.get("result", {}).get("mass_kg") == "1/6250",
                "Assigned mass check failed",
            )
            section = dispatch_section(
                store,
                dict(expected_revision=3, feature_id="part", axis="Y", offset_mm="2"),
            )
            require(
                section.get("result", {}).get("area_mm2") == "20",
                "Section check failed",
            )
            return dict(
                source_commit=manifest["source_commit"],
                source_dirty=manifest["source_dirty"],
                platform=manifest["platform"],
                python=platform.python_version(),
                files_verified=len(manifest["files"]),
                saved_solids=len(baseline["bodies"]),
                preview_save_reopen_undo="passed",
                assigned_mass_kg=mass["result"]["mass_kg"],
                section_area_mm2=section["result"]["area_mm2"],
                native_worker_starts=WORKER.starts,
                optional_mcp=mcp_environment(root),
            )
    finally:
        WORKER.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["doctor", "viewer", "command", "mcp"])
    parser.add_argument("--store", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    try:
        manifest = verify(root)
        sys.path.insert(0, str(root / "tools/ai-cad"))
        if args.action == "doctor":
            print(json.dumps(doctor(root, manifest), indent=2))
            return
        if not 1 <= args.port <= 65535:
            parser.error("Choose a port between1 and65535")
        if args.store is None:
            parser.error("--store is required; choose your editable document path")
        store = args.store.expanduser().resolve()
        if root in store.parents or store == root:
            parser.error(
                "Store documents outside the runtime bundle so updates preserve them"
            )
        script = {"viewer": "viewer.py", "command": "cad.py", "mcp": "mcp_server.py"}[
            args.action
        ]
        if args.action == "mcp" and not mcp_environment(root)["ready"]:
            raise ValueError(
                "The optional MCP environment does not match requirements.lock. Install that lock file in a virtual environment, then use its Python"
            )
        sys.argv = [script, "--store", str(store)]
        if args.action == "viewer":
            sys.argv += ["--port", str(args.port)]
        runpy.run_path(str(root / "tools/ai-cad" / script), run_name="__main__")
    except (OSError, ValueError, AssertionError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"Runtime check failed: {exc}") from exc


if __name__ == "__main__":
    main()
