"""Adapters to common topology. Original engines still perform all Booleans."""
from pathlib import Path
import math
import sys
from topology import Curve, Surface, Patch, build, TopologyError, TAU

ROOT = Path(__file__).resolve().parents[1]
for directory in ("2026-10-11-boundary-kernel", "2026-10-11-cylinder-kernel"):
    sys.path.append(str(ROOT / directory))


def pieces(edge):
    count = max(1, math.ceil(abs(edge.sweep)/(math.pi/2))) if edge.kind == "arc" else 1
    for i in range(count):
        yield (i/count, (i+1)/count)


def lifted(edge, z, lo=0, hi=1):
    return Curve(edge.kind, (*edge.point(lo), z), (*edge.point(hi), z),
                 (*edge.center, z) if edge.kind == "arc" else (), edge.radius,
                 edge.start+lo*edge.sweep, (hi-lo)*edge.sweep)


def contains(loop, point):
    """Even/odd analytic ray test; split arcs at y extrema for half-open crossings."""
    px, py = point
    crossings = 0
    for edge in loop:
        params = [0., 1.]
        if edge.kind == "arc":
            for angle in (math.pi/2, 3*math.pi/2):
                travel = ((angle-edge.start) if edge.sweep > 0 else (edge.start-angle)) % TAU
                t = travel/abs(edge.sweep)
                if 0 < t < 1:
                    params.append(t)
        for lo, hi in zip(sorted(params), sorted(params)[1:]):
            a, b = edge.point(lo), edge.point(hi)
            if (a[1] > py) == (b[1] > py):
                continue
            if edge.kind == "line":
                x = a[0]+(py-a[1])*(b[0]-a[0])/(b[1]-a[1])
            else:
                sine = max(-1., min(1., (py-edge.center[1])/edge.radius))
                angle = math.asin(sine)
                candidates = []
                for theta in (angle, math.pi-angle):
                    travel = ((theta-edge.start) if edge.sweep > 0 else (edge.start-theta)) % TAU
                    t = travel/abs(edge.sweep)
                    if lo-1e-12 <= t <= hi+1e-12:
                        candidates.append(edge.center[0]+edge.radius*math.cos(theta))
                if not candidates:
                    raise TopologyError("Cannot classify analytic cap hole")
                x = candidates[0]
            crossings += x > px
    return crossings % 2 == 1


def from_planar(body):
    patches = []
    for face in body.boundary.faces:
        loops = tuple(tuple(Curve("line", a, loop[(i+1) % len(loop)]) for i, a in enumerate(loop))
                      for loop in face.loops)
        patches.append(Patch(Surface("plane", face.normal, face.offset), loops))
    return build(patches)


def from_curved(body):
    patches = []
    for wall in body.walls:
        e = wall.edge
        for lo, hi in pieces(e):
            bottom = lifted(e, wall.z0, lo, hi)
            top = lifted(e, wall.z1, lo, hi)
            loop = (bottom, Curve("line", bottom.p1, top.p1),
                    top.reverse(), Curve("line", top.p0, bottom.p0))
            if e.kind == "line":
                dx, dy = e.p1[0]-e.p0[0], e.p1[1]-e.p0[1]
                normal = (dy, -dx, 0)
                surface = Surface("plane", normal, sum(a*b for a, b in zip(normal, bottom.p0)))
            else:
                surface = Surface("cylinder", center=e.center, radius=e.radius,
                                  orientation=1 if e.sweep > 0 else -1,
                                  angle_origin=e.start+(lo+hi)*e.sweep/2)
            patches.append(Patch(surface, (loop,)))
    for cap in body.caps:
        positives = [loop for loop in cap.region.loops if sum(e.area_integral for e in loop) > 0]
        negatives = [loop for loop in cap.region.loops if sum(e.area_integral for e in loop) < 0]
        groups = [[loop] for loop in positives]
        for hole in negatives:
            candidates = [i for i, loop in enumerate(positives) if contains(loop, hole[0].point(.37))]
            if not candidates:
                raise TopologyError("Cap hole has no outer loop")
            owner = min(candidates, key=lambda i: sum(e.area_integral for e in positives[i]))
            groups[owner].append(hole)
        for group in groups:
            loops = []
            for loop in group:
                curves = tuple(lifted(e, cap.z, lo, hi) for e in loop for lo, hi in pieces(e))
                if cap.normal < 0:
                    curves = tuple(c.reverse() for c in reversed(curves))
                loops.append(curves)
            patches.append(Patch(Surface("plane", (0, 0, cap.normal), cap.normal*cap.z), tuple(loops)))
    scale = max([1.] + [abs(x) for p in patches for loop in p.loops for e in loop
                        for point in (e.p0, e.p1) for x in point])
    tolerance = 8*max(1e-9, scale*1e-12)
    return build(patches, tolerance)


def from_model(backend, shape):
    if backend == "rational-planar":
        return from_planar(shape)
    if backend == "analytic-parallel":
        return from_curved(shape)
    raise TopologyError("Unsupported geometry backend")
