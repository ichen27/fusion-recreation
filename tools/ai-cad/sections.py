"""Exact read-only coordinate-plane sections of validated planar native solids."""

import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import re
import time
import textwrap
import xml.etree.ElementTree as ET
from drawings import NS, number
from planar_visibility import inside
from store import BINARY, CadError, Store, encode
from topology import topology_model


class SectionBudget:
    def __init__(self, work=200000, seconds=5):
        self.remaining = work
        self.deadline = time.monotonic() + seconds

    def spend(self):
        self.remaining -= 1
        if self.remaining < 0 or time.monotonic() >= self.deadline:
            raise CadError("section_limit", "Section exceeded its work or time budget")


def offset_value(value):
    if (
        not isinstance(value, str)
        or len(value) > 96
        or not re.fullmatch(r"[+-]?\d+(?:/\d+)?", value)
    ):
        raise CadError(
            "invalid_number", "Section offset must be an integer or fraction in mm"
        )
    try:
        q = F(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise CadError("invalid_number", "Invalid section offset") from exc
    if abs(q.numerator).bit_length() > 128 or q.denominator.bit_length() > 128:
        raise CadError("section_limit", "Section offset exceeds 128 bits")
    return q


def area2(loop):
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(loop, loop[1:] + loop[:1]))


def section_geometry(topology, axis, offset, budget=None):
    budget = budget or SectionBudget()
    if axis not in ("X", "Y", "Z"):
        raise CadError("invalid_command", "Section axis must be X, Y or Z")
    if len(topology["edges"]) > 256 or len(topology["faces"]) > 128:
        raise CadError(
            "section_limit", "Section supports at most256 edges and128 faces"
        )
    if any(e["curve"]["kind"] != "line" for e in topology["edges"]) or any(
        s["kind"] != "plane" for s in topology["surfaces"].values()
    ):
        raise CadError(
            "unsupported_section", "Sections currently require planar solids"
        )
    vertices = [[F(v) for v in p] for p in topology["vertices"]]
    if any(
        abs(q.numerator).bit_length() > 2048 or q.denominator.bit_length() > 2048
        for p in vertices
        for q in p
    ):
        raise CadError("section_limit", "Section coordinates exceed 2048 bits")
    depth = "XYZ".index(axis)
    h, v = [i for i in range(3) if i != depth]
    if any(p[depth] == offset for p in vertices):
        raise CadError(
            "section_degenerate",
            "The section plane passes through a native vertex; choose a different exact offset",
        )
    intersections = {}
    for index, edge in enumerate(topology["edges"]):
        budget.spend()
        a, b = [vertices[i] for i in edge["vertices"]]
        if (a[depth] < offset) != (b[depth] < offset):
            t = (offset - a[depth]) / (b[depth] - a[depth])
            intersections[index] = tuple(a[i] + t * (b[i] - a[i]) for i in (h, v))
    adjacency = {}
    for face in topology["faces"]:
        budget.spend()
        crossings = [
            intersections[u["edge"]]
            for loop in face["loops"]
            for u in loop
            if u["edge"] in intersections
        ]
        if len(crossings) % 2 or len(set(crossings)) != len(crossings):
            raise CadError(
                "section_degenerate", "Section face crossings are not simple"
            )
        # All crossings lie on the same face/section intersection line. Lexicographic
        # order is monotonic on that line; even-odd pairing handles holes and concavity.
        ordered = sorted(crossings)
        for a, b in zip(ordered[::2], ordered[1::2]):
            adjacency.setdefault(a, []).append(b)
            adjacency.setdefault(b, []).append(a)
    if not adjacency:
        raise CadError("empty_section", "The plane does not intersect material")
    if any(
        len(neighbors) != 2 or neighbors[0] == neighbors[1]
        for neighbors in adjacency.values()
    ):
        raise CadError(
            "section_degenerate",
            "Section contours branch or contain duplicate segments",
        )
    remaining = set(adjacency)
    loops = []
    while remaining:
        start = min(remaining)
        loop, current, previous = [], start, None
        while True:
            budget.spend()
            if current not in remaining:
                raise CadError(
                    "section_degenerate", "Section contour is not a simple closed loop"
                )
            remaining.remove(current)
            loop.append(current)
            following = (
                min(adjacency[current])
                if previous is None
                else next(p for p in adjacency[current] if p != previous)
            )
            previous, current = current, following
            if current == start:
                break
        if len(loop) < 3 or area2(loop) == 0:
            raise CadError("section_degenerate", "Section contour has zero area")
        loops.append(loop)
    contours = []
    for index, loop in enumerate(loops):
        nesting = sum(
            inside(loop[0], [other], budget)
            for j, other in enumerate(loops)
            if j != index
        )
        hole = nesting % 2 == 1
        if (area2(loop) > 0) == hole:
            loop = [loop[0]] + list(reversed(loop[1:]))
        contours.append(dict(points=loop, hole=hole, nesting_depth=nesting))
    total_area2 = sum(area2(c["points"]) for c in contours)
    if total_area2 <= 0:
        raise CadError("section_degenerate", "Section material has no positive area")
    moment = [F(0), F(0)]
    for contour in contours:
        loop = contour["points"]
        for a, b in zip(loop, loop[1:] + loop[:1]):
            budget.spend()
            determinant = a[0] * b[1] - b[0] * a[1]
            for i in range(2):
                moment[i] += (a[i] + b[i]) * determinant
    centroid = [offset] * 3
    centroid[h], centroid[v] = [m / (3 * total_area2) for m in moment]
    return dict(
        axis=axis,
        offset_mm=str(offset),
        horizontal_axis="XYZ"[h],
        vertical_axis="XYZ"[v],
        area_mm2=str(total_area2 / 2),
        centroid_mm=list(map(str, centroid)),
        material_regions=sum(not c["hole"] for c in contours),
        loops=[
            dict(
                points_mm=[[str(q) for q in p] for p in c["points"]],
                hole=c["hole"],
                nesting_depth=c["nesting_depth"],
            )
            for c in contours
        ],
    )


def section_svg(info):
    loops = [[[F(q) for q in p] for p in c["points_mm"]] for c in info["loops"]]
    points = [p for loop in loops for p in loop]
    bounds = [(min(p[i] for p in points), max(p[i] for p in points)) for i in range(2)]
    scale = min(
        F(520) / (bounds[0][1] - bounds[0][0]), F(430) / (bounds[1][1] - bounds[1][0])
    )
    center = [(a + b) / 2 for a, b in bounds]
    if any(
        len(value) > 80
        for value in [info["offset_mm"], info["area_mm2"], *info["centroid_mm"]]
    ):
        raise CadError("section_limit", "Exact section labels exceed80 characters")
    root = ET.Element(
        f"{{{NS}}}svg",
        dict(width="1000", height="760", viewBox="0 0 1000 760", role="img"),
    )
    root.set("font-family", "Arial, sans-serif")

    def element(parent, tag, attrs=None, text=None):
        node = ET.SubElement(parent, f"{{{NS}}}{tag}", attrs or {})
        node.text = text
        return node

    def text(x, y, value, size=14):
        element(
            root,
            "text",
            {"x": str(x), "y": str(y), "font-size": str(size), "fill": "#172b32"},
            value,
        )

    element(
        root,
        "title",
        text=f"Section {info['axis']} = {info['offset_mm']} mm: {info['feature_id']}",
    )
    element(
        root,
        "desc",
        text="Exact planar cross-section. Hatched regions are material; white openings contain no material. Selected solid only. Scale to fit; do not measure the page.",
    )
    element(root, "rect", dict(width="1000", height="760", fill="white"))
    element(
        root,
        "rect",
        dict(x="20", y="20", width="960", height="720", fill="none", stroke="#9caeb1"),
    )
    text(40, 58, "PLANAR SECTION REFERENCE", 22)
    text(
        40,
        84,
        f"{info['feature_id']} · Saved revision {info['revision']} · Millimeters",
    )
    defs = element(root, "defs")
    pattern = element(
        defs,
        "pattern",
        dict(id="hatch", width="8", height="8", patternUnits="userSpaceOnUse"),
    )
    element(
        pattern,
        "path",
        {
            "d": "M -2 2 L 2 -2 M 0 8 L 8 0 M 6 10 L 10 6",
            "stroke": "#69888e",
            "stroke-width": "0.7",
        },
    )
    commands = []
    for loop in loops:
        mapped = [
            [
                number(F(340) + (p[0] - center[0]) * scale),
                number(F(350) - (p[1] - center[1]) * scale),
            ]
            for p in loop
        ]
        if any(a == b for a, b in zip(mapped, mapped[1:] + mapped[:1])):
            raise CadError(
                "section_precision",
                "A section segment collapses at SVG display precision",
            )
        commands.append("M " + " L ".join(" ".join(p) for p in mapped) + " Z")
    element(
        root,
        "path",
        {
            "id": "section-material",
            "d": " ".join(commands),
            "fill": "url(#hatch)",
            "fill-rule": "evenodd",
            "stroke": "#172b32",
            "stroke-width": "1.2",
        },
    )
    y = 155
    for label in [
        f"{info['axis']} = {info['offset_mm']} mm",
        f"Area: {info['area_mm2']} mm²",
        "Area centroid · mm",
        *[f"{axis}: {value}" for axis, value in zip("XYZ", info["centroid_mm"])],
        f"Material regions: {info['material_regions']}",
        f"Openings: {sum(c['hole'] for c in info['loops'])}",
    ]:
        for line in textwrap.wrap(label, width=36, break_on_hyphens=False):
            text(650, y, line)
            y += 18
        y += 10
    text(
        80,
        615,
        f"{info['horizontal_axis']} right / {info['vertical_axis']} up · common scale to fit",
    )
    text(
        40,
        674,
        "Hatching marks material in the cut plane. Separate terminal solids are excluded.",
        12,
    )
    text(
        40,
        698,
        "Reference section only; no tolerances or manufacturing annotations. Do not measure the page.",
        12,
    )
    text(40, 724, f"Source model SHA-256: {info['source_model_sha256']}", 10)
    element(
        root, "metadata", text=json.dumps(info, sort_keys=True, separators=(",", ":"))
    )
    svg = ET.tostring(root, encoding="unicode")
    if len(svg.encode()) > 4 * 1024 * 1024:
        raise CadError("section_limit", "Section SVG exceeds4 MiB")
    return svg


def section_model(model, feature_id, revision, axis, offset_mm):
    offset = offset_value(offset_mm)
    topology = topology_model(model, feature_id)
    geometry = section_geometry(topology, axis, offset)
    info = dict(
        revision=revision,
        feature_id=feature_id,
        source_model_sha256=hashlib.sha256(encode(model)).hexdigest(),
        representation="planar_cross_section",
        units="mm",
        **geometry,
    )
    return {**info, "svg": section_svg(info)}


def dispatch_section(store, command):
    try:
        if (
            not isinstance(command, dict)
            or set(command) != {"expected_revision", "feature_id", "axis", "offset_mm"}
            or not isinstance(command["feature_id"], str)
        ):
            raise CadError(
                "invalid_command", "Expected revision, feature_id, axis and offset_mm"
            )
        offset = str(offset_value(command["offset_mm"]))
        if command["axis"] not in ("X", "Y", "Z"):
            raise CadError("invalid_command", "Section axis must be X, Y or Z")
        with store.locked():
            state = store.load()
            if (
                type(command["expected_revision"]) is not int
                or command["expected_revision"] != state["revision"]
            ):
                raise CadError(
                    "revision_conflict", "Refresh before creating this section"
                )
            request = dict(
                section_model=state["model"],
                feature_id=command["feature_id"],
                revision=state["revision"],
                axis=command["axis"],
                offset_mm=offset,
                section_version=1,
            )
            result = store.evaluations.get(
                BINARY,
                request,
                lambda: section_model(
                    state["model"],
                    command["feature_id"],
                    state["revision"],
                    command["axis"],
                    offset,
                ),
            )
            return {"result": result}
    except CadError as exc:
        return {"error": exc.detail}
    except (OSError, ValueError, TypeError) as exc:
        return {
            "error": dict(code="section_failed", entity="section", message=str(exc))
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--revision", type=int, required=True)
    parser.add_argument("--body", required=True)
    parser.add_argument("--axis", choices=["X", "Y", "Z"], required=True)
    parser.add_argument("--offset", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reply = dispatch_section(
        Store(args.store),
        dict(
            expected_revision=args.revision,
            feature_id=args.body,
            axis=args.axis,
            offset_mm=args.offset,
        ),
    )
    if "error" in reply:
        raise SystemExit(json.dumps(reply))
    args.output.write_text(reply["result"]["svg"], encoding="utf-8")
