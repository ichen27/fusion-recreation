"""Read-only, revision-bound export and disposable display tessellation."""

import argparse
import io
import zipfile
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from store import BINARY, CadError, Store, encode


def tessellate(model, feature_id, segments=64):
    try:
        process = subprocess.run(
            [str(BINARY), "--mesh"],
            input=encode(dict(model=model, feature_id=feature_id, segments=segments)),
            capture_output=True,
            timeout=20,
        )
        reply = json.loads(process.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise CadError("tessellation_failed", str(exc), feature_id) from exc
    if "error" in reply:
        e = reply["error"]
        raise CadError(e["code"], e["message"], e["entity"])
    if process.returncode:
        raise CadError("tessellation_failed", "Mesh process failed", feature_id)
    return reply["result"]


def display(reply, cache=None):
    """Rendering failure must not turn a successful commit into an apparent failure."""
    if "result" in reply:
        state = reply["result"]
        for body in state["bodies"]:
            if "analytic" in body:
                v = body["analytic"]["volume"]
                body["volume_approx_mm3"] = float(
                    Fraction(v["constant_mm3"])
                ) - math.pi * float(Fraction(v["pi_subtract_mm3"]))
            if "analytic" in body or "components" in body:
                try:
                    request = {
                        "model": state["model"],
                        "feature_id": body["feature_id"],
                        "segments": 64,
                    }

                    def compute():
                        return tessellate(**request)

                    body["display_mesh"] = (
                        cache.get(BINARY, request, compute)
                        if cache is not None
                        else compute()
                    )
                except CadError as exc:
                    body["display_error"] = exc.detail
    return reply


def snapshot(store, revision):
    state = store.execute({"action": "inspect"})
    if type(revision) is not int or state["revision"] != revision:
        raise CadError(
            "revision_conflict", "Refresh before exporting the saved revision"
        )
    return state


def select(store, revision, feature_id):
    state = snapshot(store, revision)
    for body in state["bodies"]:
        if body["feature_id"] == feature_id:
            return state, body
    raise CadError("missing_body", "Select a terminal solid", feature_id)


def stl_bytes(mesh):
    # ASCII preserves float64 precision; STL has no standard unit metadata.
    rows = ["solid cad_mm"]
    for ids in mesh["triangles"]:
        a, b, c = [mesh["vertices"][i] for i in ids]
        u, v = ([b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)])
        n = [
            u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0],
        ]
        length = math.hypot(*n)
        rows.append("facet normal " + " ".join(format(x / length, ".17g") for x in n))
        rows.append("outer loop")
        rows.extend(
            "vertex " + " ".join(format(x, ".17g") for x in p) for p in (a, b, c)
        )
        rows.extend(["endloop", "endfacet"])
    rows.append("endsolid cad_mm")
    return ("\n".join(rows) + "\n").encode()


def export_stl(store, revision, feature_id, segments=128):
    state, _ = select(store, revision, feature_id)
    mesh = tessellate(state["model"], feature_id, segments)
    return stl_bytes(mesh), mesh


MAX_ARCHIVE_BYTES = 64 * 1024 * 1024


def export_stl_archive(store, revision, segments=128):
    # Inspect once: every body uses the same immutable validated model snapshot,
    # even if another client commits while tessellation is running.
    state = snapshot(store, revision)
    if not state["bodies"]:
        raise CadError("missing_body", "The saved document has no solid bodies")
    stream = io.BytesIO()
    manifest = {
        "revision": revision,
        "units": "mm",
        "segments_per_circle": segments,
        "bodies": [],
    }
    total = 0
    with zipfile.ZipFile(stream, "w") as archive:

        def add(name, data):
            # Stable timestamp; safe names derive from validated IDs.
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)

        for index, body in enumerate(state["bodies"]):
            id = body["feature_id"]
            mesh = tessellate(state["model"], id, segments)
            data = stl_bytes(mesh)
            total += len(data)
            if total > MAX_ARCHIVE_BYTES:
                raise CadError(
                    "export_limit",
                    "STL archive exceeds 64 MiB before compression; export bodies individually",
                )
            filename = f"{index + 1:02d}-{id}.stl"
            add(filename, data)
            manifest["bodies"].append(
                {
                    "feature_id": id,
                    "file": filename,
                    "exact_volume_mm3": body["volume_mm3"],
                    "triangles": len(mesh["triangles"]),
                    "max_radial_error_mm": mesh["max_radial_error_mm"],
                }
            )
        add("manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())
    return stream.getvalue(), manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True)
    parser.add_argument("--revision", required=True, type=int)
    parser.add_argument("--body", required=True)
    parser.add_argument("--format", choices=["stl", "step"], required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--segments", type=int, default=128)
    args = parser.parse_args()
    try:
        store = Store(args.store)
        if args.format == "stl":
            data, mesh = export_stl(store, args.revision, args.body, args.segments)
            # Refuse accidental overwrite of any existing document/artifact.
            output = Path(args.output)
            with tempfile.TemporaryDirectory(dir=output.parent) as directory:
                staged = Path(directory) / "export.stl"
                staged.write_bytes(data)
                os.link(staged, output)
            result = {
                "triangles": len(mesh["triangles"]),
                "max_radial_error_mm": mesh["max_radial_error_mm"],
            }
        else:
            from step_export import export_step

            _, body = select(store, args.revision, args.body)
            result = export_step(body, Path(args.output))
        print(
            json.dumps(
                {
                    "result": {
                        "revision": args.revision,
                        "body": args.body,
                        "units": "mm",
                        **result,
                    }
                }
            )
        )
    except (CadError, OSError, ImportError, RuntimeError) as exc:
        print(
            json.dumps(
                {
                    "error": exc.detail
                    if isinstance(exc, CadError)
                    else {"code": "export_failed", "message": str(exc)}
                }
            )
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
