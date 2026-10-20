"""Build an original-engine runtime archive with source/file provenance and notices."""

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TOOLCHAIN = "1.85.1"
ENGINE = Path("crates/model-engine/target/release/model-engine")
# Runtime modules are explicit: never package private documents, caches or test logs.
MODULES = "cad clearance drawings edge_measurements engine_transport exports interference intent inventory mass_properties materials mcp_server measurements planar_visibility preview_jobs preview_worker result_cache sections selection store topology viewer viewer_server step_export frustum_export revolve_export topology_step".split()


def run(*args, env=None):
    return subprocess.check_output(args, cwd=ROOT, env=env, text=True).strip()


def build(output, development=False):
    output = output.resolve()
    if output.exists():
        raise ValueError("Output already exists; choose a new archive path")
    dirty = bool(run("git", "status", "--porcelain", "--untracked-files=normal"))
    if dirty and not development:
        raise ValueError(
            "Commit source changes first, or use --development for a marked scratch build"
        )
    commit = run("git", "rev-parse", "HEAD")
    timestamp = int(run("git", "show", "-s", "--format=%ct", "HEAD"))
    env = os.environ.copy()
    cargo_home = Path(env.get("CARGO_HOME", str(Path.home() / ".cargo"))).resolve()
    env["CARGO_ENCODED_RUSTFLAGS"] = "\x1f".join(
        [f"--remap-path-prefix={ROOT}=/src", f"--remap-path-prefix={cargo_home}=/cargo"]
    )
    subprocess.run(
        [
            "cargo",
            f"+{TOOLCHAIN}",
            "build",
            "--release",
            "--locked",
            "--manifest-path",
            "crates/model-engine/Cargo.toml",
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )
    metadata = json.loads(
        run(
            "cargo",
            f"+{TOOLCHAIN}",
            "metadata",
            "--locked",
            "--format-version",
            "1",
            "--manifest-path",
            "crates/model-engine/Cargo.toml",
            env=env,
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".cad-package-", dir=output.parent
    ) as directory:
        stage = Path(directory) / "original-cad"
        stage.mkdir()

        def copy(source, destination):
            target = stage / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            target.chmod(0o755 if destination == ENGINE else 0o644)

        copy(ROOT / ENGINE, ENGINE)
        copy(ROOT / "tools/ai-cad/runtime_launcher.py", Path("cad.py"))
        copy(ROOT / "tools/ai-cad/runtime-bundle.md", Path("README.md"))
        copy(ROOT / "tools/ai-cad/requirements.lock", Path("requirements.lock"))
        copy(ROOT / "tools/ai-cad/step-requirements.txt", Path("step-requirements.txt"))
        copy(ROOT / "crates/model-engine/Cargo.lock", Path("engine-Cargo.lock"))
        for module in MODULES:
            rel = Path(f"tools/ai-cad/{module}.py")
            copy(ROOT / rel, rel)
        for source in sorted((ROOT / "tools/ai-cad/web").iterdir()):
            if source.is_file() and source.suffix in (".js", ".mjs", ".css", ".html"):
                copy(source, source.relative_to(ROOT))
        copy(
            ROOT / "examples/ai-cad/materials/source.cad.json",
            Path("samples/materials.cad.json"),
        )
        copy(
            ROOT / "examples/ai-cad/planar-sections/source.cad.json",
            Path("samples/cavity.cad.json"),
        )
        notices = []
        for package in metadata["packages"]:
            if package["source"] is None:
                continue
            folder = Path(package["manifest_path"]).parent
            files = [
                p
                for p in sorted(folder.iterdir())
                if p.is_file()
                and p.name.upper().startswith(("LICENSE", "COPYING", "NOTICE"))
            ]
            if not files:
                raise ValueError(
                    f"Missing third-party notice files for {package['name']}"
                )
            destinations = []
            for file in files:
                destination = (
                    Path("third-party")
                    / f"{package['name']}-{package['version']}"
                    / file.name
                )
                copy(file, destination)
                destinations.append(str(destination))
            notices.append(
                dict(
                    package=package["name"],
                    version=package["version"],
                    license=package["license"],
                    repository=package["repository"],
                    files=destinations,
                )
            )
        sysroot = Path(run("rustc", f"+{TOOLCHAIN}", "--print", "sysroot"))
        for name in ["LICENSE-MIT", "LICENSE-APACHE", "COPYRIGHT"]:
            copy(sysroot / "share/doc/rust" / name, Path("third-party/rust") / name)
        (stage / "third-party/index.json").write_text(
            json.dumps(dict(rust_toolchain=TOOLCHAIN, packages=notices), indent=2)
            + "\n"
        )
        files = {
            str(p.relative_to(stage)): dict(
                sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                bytes=p.stat().st_size,
                executable=os.access(p, os.X_OK),
            )
            for p in sorted(stage.rglob("*"))
            if p.is_file()
        }
        manifest = dict(
            format_version=1,
            source_repository="https://github.com/ichen27/fusion-recreation",
            source_commit=commit,
            source_dirty=dirty,
            platform=dict(
                system=platform.system(),
                machine=platform.machine(),
                tested_os=platform.mac_ver()[0]
                if platform.system() == "Darwin"
                else platform.release(),
            ),
            rustc=run("rustc", f"+{TOOLCHAIN}", "--version"),
            files=files,
        )
        (stage / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        # Explicit normalized metadata makes archives stable for identical build bytes.
        data = io.BytesIO()
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=data, mtime=timestamp
        ) as zipped:
            with tarfile.open(fileobj=zipped, mode="w") as archive:
                for path in sorted(stage.rglob("*")):
                    if not path.is_file():
                        continue
                    entry = tarfile.TarInfo(
                        "original-cad/" + str(path.relative_to(stage))
                    )
                    content = path.read_bytes()
                    entry.size = len(content)
                    entry.mtime = timestamp
                    entry.mode = 0o755 if os.access(path, os.X_OK) else 0o644
                    archive.addfile(entry, io.BytesIO(content))
        output.write_bytes(data.getvalue())
    print(
        json.dumps(
            dict(
                archive=str(output),
                sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                bytes=output.stat().st_size,
                source_commit=commit,
                source_dirty=dirty,
            )
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--development",
        action="store_true",
        help="Permit uncommitted source and mark the manifest; never a release artifact",
    )
    args = parser.parse_args()
    build(args.output, args.development)
