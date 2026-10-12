"""Disposable analytic edge/face incidence model; no geometry Boolean operations."""
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
import math

TAU = 2 * math.pi


class TopologyError(ValueError):
    pass


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def distance(a, b):
    return math.sqrt(float(dot(sub(a, b), sub(a, b))))


def close(a, b, tolerance):
    return a == b if tolerance == 0 else distance(a, b) <= tolerance


@dataclass(frozen=True)
class Curve:
    kind: str
    p0: tuple
    p1: tuple
    center: tuple = ()
    radius: float = 0
    start: float = 0
    sweep: float = 0

    def point(self, t):
        if self.kind == "line":
            return tuple(a + t*(b-a) for a, b in zip(self.p0, self.p1))
        angle = self.start + t*self.sweep
        return (self.center[0] + self.radius*math.cos(angle),
                self.center[1] + self.radius*math.sin(angle), self.center[2])

    def reverse(self):
        return Curve(self.kind, self.p1, self.p0, self.center, self.radius,
                     self.start+self.sweep, -self.sweep)

    def part(self, t0, t1):
        return Curve(self.kind, self.point(t0), self.point(t1), self.center, self.radius,
                     self.start+t0*self.sweep, (t1-t0)*self.sweep)

    def parameter(self, p, tolerance):
        if self.kind == "line":
            delta = sub(self.p1, self.p0)
            axis = max(range(3), key=lambda i: abs(delta[i]))
            if delta[axis] == 0:
                raise TopologyError("Zero length line")
            t = (p[axis]-self.p0[axis])/delta[axis]
            return t if 0 < t < 1 and close(self.point(t), p, tolerance) else None
        if abs(p[2]-self.center[2]) > tolerance:
            return None
        if abs(math.hypot(p[0]-self.center[0], p[1]-self.center[1])-self.radius) > tolerance:
            return None
        angle = math.atan2(p[1]-self.center[1], p[0]-self.center[0])
        travel = ((angle-self.start) if self.sweep > 0 else (self.start-angle)) % TAU
        t = travel/abs(self.sweep)
        return t if 0 < t < 1 and close(self.point(t), p, tolerance*2) else None

    def area_vector(self):
        if self.kind == "line":
            return tuple(v/2 for v in cross(self.p0, self.p1))
        a, b = self.start, self.start+self.sweep
        x, y, z = self.center
        dz = (self.radius*x*(math.sin(b)-math.sin(a)) +
              self.radius*y*(math.cos(a)-math.cos(b)) + self.radius**2*self.sweep)/2
        return (-z*(self.p1[1]-self.p0[1])/2, z*(self.p1[0]-self.p0[0])/2, dz)


@dataclass(frozen=True)
class Surface:
    kind: str
    normal: tuple = ()
    offset: object = 0
    center: tuple = ()
    radius: float = 0
    orientation: int = 1
    angle_origin: float = 0


@dataclass(frozen=True)
class Patch:
    surface: Surface
    loops: tuple


@dataclass(frozen=True)
class Edge:
    start: int
    end: int
    curve: Curve


@dataclass(frozen=True)
class Use:
    edge: int
    forward: bool


@dataclass(frozen=True)
class Face:
    surface: Surface
    loops: tuple


@dataclass(frozen=True)
class Boundary:
    vertices: tuple
    edges: tuple
    faces: tuple
    tolerance: float = 0

    def directed(self, use):
        e = self.edges[use.edge]
        return (e.start, e.end, e.curve) if use.forward else (e.end, e.start, e.curve.reverse())

    def owners(self):
        result = defaultdict(list)
        for face_id, face in enumerate(self.faces):
            for loop in face.loops:
                for use in loop:
                    result[use.edge].append((face_id, use.forward))
        return result

    def shells(self):
        graph = {i: set() for i in range(len(self.faces))}
        for owners in self.owners().values():
            ids = {i for i, _ in owners}
            for i in ids:
                graph[i].update(ids - {i})
        components = []
        unseen = set(graph)
        while unseen:
            stack = [min(unseen)]
            found = set()
            while stack:
                i = stack.pop()
                if i in found:
                    continue
                found.add(i)
                stack.extend(graph[i]-found)
            unseen -= found
            components.append(tuple(sorted(found)))
        return tuple(components)

    def euler(self, shell):
        edge_ids = {u.edge for i in shell for loop in self.faces[i].loops for u in loop}
        vertex_ids = {v for i in edge_ids for v in (self.edges[i].start, self.edges[i].end)}
        # A face with h holes has Euler contribution 1-h.
        return len(vertex_ids)-len(edge_ids)+sum(2-len(self.faces[i].loops) for i in shell)

    def validate(self):
        errors = set()
        if not math.isfinite(self.tolerance) or self.tolerance < 0:
            return ("Invalid tolerance",)
        def finite(value):
            return type(value) in (int, Fraction) or (type(value) is float and math.isfinite(value))
        values = [x for p in self.vertices for x in p]
        for e in self.edges:
            values.extend((*e.curve.p0, *e.curve.p1, *e.curve.center,
                           e.curve.radius, e.curve.start, e.curve.sweep))
        for face in self.faces:
            s = face.surface
            values.extend((*s.normal, *s.center, s.offset, s.radius, s.orientation, s.angle_origin))
        if not all(finite(x) for x in values):
            return ("Nonfinite geometry",)
        if any(len(p) != 3 for p in self.vertices) or any(
                len(e.curve.p0) != 3 or len(e.curve.p1) != 3 or
                (e.curve.kind == "arc" and len(e.curve.center) != 3) for e in self.edges):
            return ("Invalid coordinate dimension",)
        if any((f.surface.kind == "plane" and len(f.surface.normal) != 3) or
               (f.surface.kind == "cylinder" and len(f.surface.center) != 2) for f in self.faces):
            return ("Invalid surface dimension",)
        used_vertices = set()
        for e in self.edges:
            if any(type(v) is not int or not 0 <= v < len(self.vertices) for v in (e.start, e.end)):
                errors.add("Invalid vertex reference")
                continue
            used_vertices.update((e.start, e.end))
            if e.start == e.end or close(e.curve.p0, e.curve.p1, self.tolerance):
                errors.add("Degenerate edge")
            if e.curve.kind not in ("line", "arc"):
                errors.add("Unsupported curve")
            if not close(e.curve.p0, self.vertices[e.start], self.tolerance*2) or not close(
                    e.curve.p1, self.vertices[e.end], self.tolerance*2):
                errors.add("Curve/vertex mismatch")
            if e.curve.kind == "arc":
                if e.curve.radius <= 0 or not 0 < abs(e.curve.sweep) <= math.pi/2+1e-10:
                    errors.add("Invalid arc range")
                if not close(e.curve.point(0), e.curve.p0, self.tolerance*2) or not close(
                        e.curve.point(1), e.curve.p1, self.tolerance*2):
                    errors.add("Arc endpoint mismatch")
        if errors:
            return tuple(sorted(errors))
        if used_vertices != set(range(len(self.vertices))):
            errors.add("Unused vertex")
        for face in self.faces:
            if not face.loops or any(not loop for loop in face.loops):
                errors.add("Empty face loop")
                continue
            seen = set()
            for number, loop in enumerate(face.loops):
                if any(type(u.edge) is not int or not 0 <= u.edge < len(self.edges) for u in loop):
                    errors.add("Invalid edge reference")
                    continue
                if any(type(u.forward) is not bool for u in loop):
                    errors.add("Invalid edge orientation flag")
                directed = [self.directed(u) for u in loop]
                for i, (a, b, curve) in enumerate(directed):
                    if b != directed[(i+1) % len(directed)][0]:
                        errors.add("Open face loop")
                    if a in seen:
                        errors.add("Repeated face vertex")
                    seen.add(a)
                    surface = face.surface
                    if surface.kind == "plane":
                        scale = math.sqrt(float(dot(surface.normal, surface.normal)))
                        if scale == 0:
                            errors.add("Zero plane normal")
                        for p in (curve.p0, curve.point(Fraction(1, 2)), curve.p1):
                            if abs(dot(surface.normal, p)-surface.offset) > self.tolerance*4*scale:
                                errors.add("Curve off plane")
                    elif surface.kind == "cylinder":
                        if surface.radius <= 0 or surface.orientation not in (-1, 1):
                            errors.add("Invalid cylinder")
                        if curve.kind == "line" and not close(curve.p0[:2], curve.p1[:2], self.tolerance):
                            errors.add("Nonaxial cylinder line")
                        for p in (curve.p0, curve.point(.5), curve.p1):
                            if abs(math.hypot(p[0]-surface.center[0], p[1]-surface.center[1])
                                   - surface.radius) > self.tolerance*4:
                                errors.add("Curve off cylinder")
                    else:
                        errors.add("Unsupported surface")
                surface = face.surface
                if surface.kind == "plane":
                    area = tuple(sum(c.area_vector()[i] for _, _, c in directed) for i in range(3))
                    oriented = dot(area, surface.normal)
                elif surface.kind == "cylinder":
                    uv = []
                    for _, _, c in directed:
                        p = c.p0
                        angle = math.atan2(p[1]-surface.center[1], p[0]-surface.center[0])
                        angle = surface.angle_origin + (angle-surface.angle_origin+math.pi) % TAU-math.pi
                        uv.append((angle, p[2]))
                    oriented = surface.orientation*sum(
                        a[0]*b[1]-b[0]*a[1] for a, b in zip(uv, uv[1:]+uv[:1]))
                else:
                    continue
                if oriented*(1 if number == 0 else -1) <= 0:
                    errors.add("Incorrect face orientation")
        if "Invalid edge reference" in errors:
            return tuple(sorted(errors))
        owners = self.owners()
        for i in range(len(self.edges)):
            entries = owners.get(i, [])
            if len(entries) != 2 or entries[0][0] == entries[-1][0]:
                errors.add("Open or nonmanifold edge")
            elif entries[0][1] == entries[1][1]:
                errors.add("Inconsistent edge orientation")
        if "Open or nonmanifold edge" not in errors:
            links = defaultdict(lambda: defaultdict(list))
            for edge_id, entries in owners.items():
                a, b = [i for i, _ in entries]
                for vertex in (self.edges[edge_id].start, self.edges[edge_id].end):
                    links[vertex][a].append(b)
                    links[vertex][b].append(a)
            for graph in links.values():
                if any(len(adj) != 2 for adj in graph.values()):
                    errors.add("Nonmanifold vertex")
                found = set()
                stack = [next(iter(graph))]
                while stack:
                    current = stack.pop()
                    if current not in found:
                        found.add(current)
                        stack.extend(graph[current])
                if len(found) != len(graph):
                    errors.add("Disconnected vertex link")
            for shell in self.shells():
                euler = self.euler(shell)
                if euler > 2 or euler % 2:
                    errors.add("Invalid shell Euler characteristic")
        return tuple(sorted(errors))

    def summary(self):
        return {"vertices": len(self.vertices), "edges": len(self.edges), "faces": len(self.faces),
                "shells": len(self.shells()), "shell_euler": [self.euler(s) for s in self.shells()],
                "tolerance_mm": self.tolerance, "errors": list(self.validate())}


def build(patches, tolerance=0):
    """Conform edge subdivisions globally, then share analytic edges and vertex indices."""
    vertices = []
    def vertex(p):
        matches = [i for i, q in enumerate(vertices) if close(p, q, tolerance)]
        if len(matches) > 1:
            raise TopologyError("Ambiguous vertex clustering")
        if matches:
            return matches[0]
        vertices.append(p)
        return len(vertices)-1
    for patch in patches:
        for loop in patch.loops:
            for curve in loop:
                vertex(curve.p0)
                vertex(curve.p1)
    edges = []
    by_ends = defaultdict(list)
    faces = []
    for patch in patches:
        loops = []
        for loop in patch.loops:
            uses = []
            for curve in loop:
                params = [Fraction(0), Fraction(1)]
                for p in vertices:
                    t = curve.parameter(p, tolerance)
                    if t is not None and not close(curve.point(t), curve.p0, tolerance) and not close(
                            curve.point(t), curve.p1, tolerance):
                        params.append(t)
                unique = []
                for t in sorted(params):
                    if not unique or not close(curve.point(t), curve.point(unique[-1]), tolerance):
                        unique.append(t)
                for lo, hi in zip(unique, unique[1:]):
                    part = curve.part(lo, hi)
                    a, b = vertex(part.p0), vertex(part.p1)
                    if a == b:
                        raise TopologyError("Unresolved edge interval")
                    forward = a < b
                    key = (min(a, b), max(a, b), part.kind)
                    canonical = part if forward else part.reverse()
                    candidates = [i for i in by_ends[key] if (
                        part.kind == "line" or (
                            close(edges[i].curve.center, canonical.center, tolerance) and
                            abs(edges[i].curve.radius-canonical.radius) <= tolerance and
                            close(edges[i].curve.point(.5), canonical.point(.5), tolerance*2)))]
                    if len(candidates) > 1:
                        raise TopologyError("Ambiguous analytic edge identity")
                    if candidates:
                        edge_id = candidates[0]
                    else:
                        edge_id = len(edges)
                        edges.append(Edge(key[0], key[1], canonical))
                        by_ends[key].append(edge_id)
                    uses.append(Use(edge_id, forward))
            loops.append(tuple(uses))
        faces.append(Face(patch.surface, tuple(loops)))
    result = Boundary(tuple(vertices), tuple(edges), tuple(faces), tolerance)
    errors = result.validate()
    if errors:
        raise TopologyError("; ".join(errors))
    return result
