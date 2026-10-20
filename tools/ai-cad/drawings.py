"""Revision-bound orthographic reference sheets from validated native topology."""

import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import textwrap
import xml.etree.ElementTree as ET
from store import BINARY, CadError, Store, encode
from topology import topology_model

NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
VIEWS = [("top", 0, 1, 250, 235), ("front", 0, 2, 250, 520), ("right", 1, 2, 750, 520)]


def number(value):
    return format(float(value), ".12g")


def drawing_model(model, feature_id, revision):
    topology = topology_model(model, feature_id)
    vertices = [[F(v) for v in p] for p in topology["vertices"]]
    bounds = [
        [min(p[i] for p in vertices) for i in range(3)],
        [max(p[i] for p in vertices) for i in range(3)],
    ]
    extents = [bounds[1][i] - bounds[0][i] for i in range(3)]
    if any(v <= 0 for v in extents):
        raise CadError("drawing_geometry", "Expected a solid with positive XYZ extents")
    if any(len(str(v)) > 80 for v in extents):
        raise CadError(
            "drawing_limit", "An exact extent exceeds the reference-sheet label limit"
        )
    # Normalize in exact arithmetic before converting to bounded SVG display coordinates.
    scale = min(
        F(360) / max(extents[0], extents[1]), F(160) / max(extents[1], extents[2])
    )
    center = [(bounds[0][i] + bounds[1][i]) / 2 for i in range(3)]
    fingerprint = hashlib.sha256(encode(model)).hexdigest()
    info = dict(
        revision=revision,
        feature_id=feature_id,
        units="mm",
        source_model_sha256=fingerprint,
        bounds_mm=[[str(v) for v in p] for p in bounds],
        extents_mm=[str(v) for v in extents],
        representation="orthographic_all_edges",
        scale_policy="fit_sheet_not_for_measurement",
        views=[],
    )
    root = ET.Element(
        f"{{{NS}}}svg",
        dict(width="1000", height="760", viewBox="0 0 1000 760", role="img"),
    )

    def element(parent, tag, attrs=None, text=None):
        node = ET.SubElement(parent, f"{{{NS}}}{tag}", attrs or {})
        node.text = text
        return node

    def text(x, y, value, size=14, parent=root):
        return element(
            parent,
            "text",
            {"x": str(x), "y": str(y), "font-size": str(size), "fill": "#172b32"},
            value,
        )

    root.set("font-family", "Arial, sans-serif")
    element(
        root,
        "title",
        text=f"Orthographic reference sheet: {feature_id}, revision {revision}",
    )
    element(
        root,
        "desc",
        text="Top, front and right projections. All native edges are shown, including occluded edges and smooth surface seams. No hidden-line removal. Scale to fit; use exact dimension labels, not page measurements.",
    )
    element(root, "rect", dict(x="0", y="0", width="1000", height="760", fill="white"))
    element(
        root,
        "rect",
        dict(x="20", y="20", width="960", height="720", fill="none", stroke="#9caeb1"),
    )
    text(40, 58, "ORTHOGRAPHIC REFERENCE SHEET", 22)
    text(40, 84, f"{feature_id}  ·  Saved revision {revision}  ·  Millimeters")
    element(root, "line", dict(x1="40", y1="100", x2="960", y2="100", stroke="#9caeb1"))
    for name, h, v, cx, cy in VIEWS:

        def project(point):
            return [
                F(cx) + (point[h] - center[h]) * scale,
                F(cy) - (point[v] - center[v]) * scale,
            ]

        group = element(
            root,
            "g",
            {
                "id": f"view-{name}",
                "fill": "none",
                "stroke": "#172b32",
                "stroke-width": "1.2",
                "stroke-linejoin": "round",
                "stroke-linecap": "round",
            },
        )
        count = dict(
            name=name,
            horizontal_axis="XYZ"[h],
            vertical_axis="XYZ"[v],
            line_edges=0,
            arc_edges=0,
            collapsed_edges=0,
        )
        depth = next(i for i in range(3) if i not in (h, v))
        for index, edge in enumerate(topology["edges"]):
            a, b = [vertices[i] for i in edge["vertices"]]
            start, end = project(a), project(b)
            if start == end:
                count["collapsed_edges"] += 1
                continue
            p, q = [list(map(number, point)) for point in (start, end)]
            if p == q:
                raise CadError(
                    "drawing_precision",
                    "A projected edge collapses at SVG display precision",
                    feature_id,
                )
            curve = edge["curve"]
            path = f"M {p[0]} {p[1]} "
            if curve["kind"] == "quarter_circle" and curve["axis"][depth]:
                c = project(list(map(F, curve["center"])))
                u = [start[i] - c[i] for i in range(2)]
                w = [end[i] - c[i] for i in range(2)]
                sweep = int(u[0] * w[1] - u[1] * w[0] > 0)
                radius = number(F(curve["radius"]) * scale)
                path += f"A {radius} {radius} 0 0 {sweep} {q[0]} {q[1]}"
                count["arc_edges"] += 1
            elif curve["kind"] in ("line", "quarter_circle"):
                path += f"L {q[0]} {q[1]}"
                count["line_edges"] += 1
            else:
                raise CadError(
                    "unsupported_drawing", "Unsupported native edge curve", feature_id
                )
            element(group, "path", {"d": path, "data-edge-index": str(index)})
        text(
            cx - 180,
            cy + 116,
            f"{name.title()}  ·  {'XYZ'[h]} right / {'XYZ'[v]} up",
            13,
        )
        info["views"].append(count)
    text(550, 145, "EXACT OVERALL DIMENSIONS", 16)
    y = 175
    for axis, value in zip("XYZ", extents):
        for line in textwrap.wrap(
            f"{axis}: {value} mm", width=45, break_on_hyphens=False
        ):
            text(550, y, line, 13)
            y += 18
        y += 8
    text(550, 310, "Common scale to fit · do not measure the page", 12)
    element(root, "line", dict(x1="40", y1="665", x2="960", y2="665", stroke="#9caeb1"))
    text(
        40,
        688,
        "All native edges shown, including occluded edges and smooth surface seams. No hidden-line removal.",
        12,
    )
    text(
        40,
        707,
        "Reference views only. Section views, tolerances and manufacturing annotations are not included.",
        12,
    )
    text(40, 726, f"Source model SHA-256: {fingerprint}", 10)
    element(
        root, "metadata", text=json.dumps(info, sort_keys=True, separators=(",", ":"))
    )
    svg = ET.tostring(root, encoding="unicode")
    if len(svg.encode()) > 4 * 1024 * 1024:
        raise CadError("drawing_limit", "SVG reference sheet exceeds 4 MiB")
    return {**info, "svg": svg}


def dispatch_drawing(store, command):
    try:
        if (
            not isinstance(command, dict)
            or set(command) != {"expected_revision", "feature_id"}
            or not isinstance(command["feature_id"], str)
        ):
            raise CadError("invalid_command", "Expected revision and feature_id")
        with store.locked():
            state = store.load()
            if (
                type(command["expected_revision"]) is not int
                or command["expected_revision"] != state["revision"]
            ):
                raise CadError(
                    "revision_conflict", "Refresh before exporting this reference sheet"
                )
            request = dict(
                drawing_model=state["model"],
                feature_id=command["feature_id"],
                revision=state["revision"],
                drawing_version=1,
            )
            result = store.evaluations.get(
                BINARY,
                request,
                lambda: drawing_model(
                    state["model"], command["feature_id"], state["revision"]
                ),
            )
            return {"result": result}
    except CadError as exc:
        return {"error": exc.detail}
    except (OSError, ValueError, TypeError) as exc:
        return {
            "error": {
                "code": "drawing_failed",
                "entity": "drawing",
                "message": str(exc),
            }
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--revision", type=int, required=True)
    parser.add_argument("--body", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reply = dispatch_drawing(
        Store(args.store), dict(expected_revision=args.revision, feature_id=args.body)
    )
    if "error" in reply:
        raise SystemExit(json.dumps(reply))
    args.output.write_text(reply["result"]["svg"], encoding="utf-8")
