"""Exact orthographic visibility intervals for validated planar native topology.

This is derived drawing data. It never modifies the authoritative solid and does
not approximate curved surfaces. Observer direction is a signed coordinate axis.
"""

from fractions import Fraction as F
import time
from store import CadError


class Budget:
    def __init__(self, work=500000, seconds=5):
        self.remaining = work
        self.deadline = time.monotonic() + seconds

    def spend(self):
        self.remaining -= 1
        if self.remaining < 0:
            raise CadError(
                "drawing_limit", "Planar visibility exceeds its exact-work budget"
            )
        if time.monotonic() >= self.deadline:
            raise CadError(
                "drawing_timeout", "Planar visibility exceeded its time budget"
            )


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def subtract(a, b):
    return [a[i] - b[i] for i in range(2)]


def inside(point, rings, budget):
    contained = False
    for ring in rings:
        odd = False
        for a, b in zip(ring, ring[1:] + ring[:1]):
            budget.spend()
            if cross(subtract(b, a), subtract(point, a)) == 0 and all(
                min(a[i], b[i]) <= point[i] <= max(a[i], b[i]) for i in range(2)
            ):
                return True  # A closed face includes its boundary, including hole rims.
            if (a[1] > point[1]) != (b[1] > point[1]):
                x = a[0] + (point[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
                if x > point[0]:
                    odd = not odd
        contained ^= odd
    return contained


def intervals(topology, horizontal, vertical, observer_sign, budget=None):
    budget = budget or Budget()
    if observer_sign not in (-1, 1) or sorted((horizontal, vertical)) not in (
        [0, 1],
        [0, 2],
        [1, 2],
    ):
        raise ValueError("Expected distinct coordinate axes and observer sign")
    if len(topology["edges"]) > 256 or len(topology["faces"]) > 128:
        raise CadError(
            "drawing_limit",
            "Planar visibility supports at most 256 edges and 128 faces",
        )
    if any(e["curve"]["kind"] != "line" for e in topology["edges"]) or any(
        s["kind"] != "plane" for s in topology["surfaces"].values()
    ):
        raise CadError(
            "unsupported_drawing",
            "Hidden-line classification currently requires planar solids; use all native edges for curved solids",
        )
    depth = next(i for i in range(3) if i not in (horizontal, vertical))

    def value(text):
        q = F(text)
        if abs(q.numerator).bit_length() > 2048 or q.denominator.bit_length() > 2048:
            raise CadError(
                "drawing_limit", "Planar visibility coefficients exceed 2048 bits"
            )
        return q

    vertices = [[value(v) for v in p] for p in topology["vertices"]]

    def project(p):
        return [p[horizontal], p[vertical]]

    faces = []
    for face in topology["faces"]:
        surface = topology["surfaces"][face["surface"]]
        normal = list(map(value, surface["normal"]))
        if not normal[depth]:
            continue
        rings = []
        for loop in face["loops"]:
            rings.append(
                [
                    project(
                        vertices[
                            topology["edges"][u["edge"]]["vertices"][
                                0 if u["forward"] else 1
                            ]
                        ]
                    )
                    for u in loop
                ]
            )
        points = [p for ring in rings for p in ring]
        box = [(min(p[i] for p in points), max(p[i] for p in points)) for i in range(2)]
        faces.append((normal, value(surface["offset"]), rings, box))
    result = []
    for edge in topology["edges"]:
        a, b = [vertices[i] for i in edge["vertices"]]
        start, end = project(a), project(b)
        if start == end:
            result.append([])
            continue
        delta = subtract(end, start)
        full_delta = [b[i] - a[i] for i in range(3)]
        cuts = {F(0), F(1)}
        candidates = []
        for normal, offset, rings, box in faces:
            budget.spend()
            if any(
                max(start[i], end[i]) < box[i][0] or min(start[i], end[i]) > box[i][1]
                for i in range(2)
            ):
                continue
            c = (
                offset
                - normal[horizontal] * a[horizontal]
                - normal[vertical] * a[vertical]
            ) / normal[depth] - a[depth]
            slope = (
                -(
                    normal[horizontal] * full_delta[horizontal]
                    + normal[vertical] * full_delta[vertical]
                )
                / normal[depth]
                - full_delta[depth]
            )
            candidates.append((c, slope, rings, box))
            if slope:
                t = -c / slope
                if 0 < t < 1:
                    cuts.add(t)
            for ring in rings:
                for p, q in zip(ring, ring[1:] + ring[:1]):
                    budget.spend()
                    segment = subtract(q, p)
                    denominator = cross(delta, segment)
                    difference = subtract(p, start)
                    if denominator:
                        t = cross(difference, segment) / denominator
                        u = cross(difference, delta) / denominator
                        if 0 < t < 1 and 0 <= u <= 1:
                            cuts.add(t)
                    elif cross(difference, delta) == 0:
                        axis = 0 if delta[0] else 1
                        for point in (p, q):
                            t = (point[axis] - start[axis]) / delta[axis]
                            if 0 < t < 1:
                                cuts.add(t)
        ordered = sorted(cuts)
        pieces = []
        for lo, hi in zip(ordered, ordered[1:]):
            midpoint = (lo + hi) / 2
            point = [start[i] + midpoint * delta[i] for i in range(2)]
            hidden = False
            for c, slope, rings, box in candidates:
                budget.spend()
                if observer_sign * (c + slope * midpoint) <= 0 or any(
                    not low <= point[i] <= high for i, (low, high) in enumerate(box)
                ):
                    continue
                if inside(point, rings, budget):
                    hidden = True
                    break
            if pieces and pieces[-1][2] == hidden:
                pieces[-1] = (pieces[-1][0], hi, hidden)
            else:
                pieces.append((lo, hi, hidden))
        result.append(pieces)
    return result


def drawing_segments(topology, horizontal, vertical, observer_sign, budget):
    """Merge collinear projected ink; visible coverage takes precedence.

    Each output keeps one exact native-edge interval as representative provenance.
    Native visibility intervals themselves are unchanged by this drawing step.
    """
    spans = intervals(topology, horizontal, vertical, observer_sign, budget)
    vertices = [[F(v) for v in p] for p in topology["vertices"]]
    groups = {}
    for index, (edge, pieces) in enumerate(zip(topology["edges"], spans)):
        a, b = [vertices[i] for i in edge["vertices"]]
        start = [a[horizontal], a[vertical]]
        delta = [b[horizontal] - a[horizontal], b[vertical] - a[vertical]]
        if not pieces:
            continue
        normal = [delta[1], -delta[0]]
        divisor = normal[0] or normal[1]
        key = (
            normal[0] / divisor,
            normal[1] / divisor,
            (normal[0] * start[0] + normal[1] * start[1]) / divisor,
        )
        axis = 0 if delta[0] else 1
        for lo, hi, hidden in pieces:
            low, high = sorted([start[axis] + t * delta[axis] for t in (lo, hi)])
            groups.setdefault(key, []).append((low, high, index, hidden, axis))
    merged = []
    for group in groups.values():
        ends = sorted({v for item in group for v in item[:2]})
        for low, high in zip(ends, ends[1:]):
            midpoint = (low + high) / 2
            covering = []
            for item in group:
                budget.spend()
                if item[0] < midpoint < item[1]:
                    covering.append(item)
            if not covering:
                continue
            chosen = min(covering, key=lambda p: (p[3], p[2]))
            _, _, index, hidden, axis = chosen
            a, b = [vertices[i] for i in topology["edges"][index]["vertices"]]
            coordinate = horizontal if axis == 0 else vertical
            lo, hi = sorted(
                (v - a[coordinate]) / (b[coordinate] - a[coordinate])
                for v in (low, high)
            )
            if (
                merged
                and merged[-1][0] == index
                and merged[-1][3] == hidden
                and (merged[-1][2] == lo or merged[-1][1] == hi)
            ):
                previous = merged.pop()
                merged.append(
                    (index, min(lo, previous[1]), max(hi, previous[2]), hidden)
                )
            else:
                merged.append((index, lo, hi, hidden))
    return sorted(merged, key=lambda p: (not p[3], p[0], p[1])), sum(
        not p for p in spans
    )
