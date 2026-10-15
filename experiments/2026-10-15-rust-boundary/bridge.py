"""Lossless bridge to the previous shared topology; never performs a Boolean."""
from fractions import Fraction as F
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-10-12-shared-topology"))
from topology import Boundary, Curve, Edge, Face, Surface, Use, cross, dot


def scalar(value):
    if type(value) not in (int, F):
        raise ValueError("Rust planar bridge requires exact rational coordinates")
    return str(value)


def encode(boundary):
    if boundary.tolerance != 0 or boundary.validate():
        raise ValueError("Expected a valid exact shared boundary")
    if any(e.curve.kind != "line" for e in boundary.edges) or any(
            f.surface.kind != "plane" for f in boundary.faces):
        raise ValueError("Curved geometry is unsupported by the planar Rust probe")
    return {
        "vertices": [[scalar(x) for x in p] for p in boundary.vertices],
        "edges": [{"kind": "line", "vertices": [e.start, e.end]} for e in boundary.edges],
        "faces": [{"kind": "plane", "normal": list(map(scalar, f.surface.normal)),
                   "offset": scalar(f.surface.offset),
                   "loops": [[{"edge": u.edge, "forward": u.forward} for u in loop]
                             for loop in f.loops]} for f in boundary.faces],
    }


def decode(data):
    # Direct construction retains the Rust incidences; build() could repair subdivisions.
    vertices = tuple(tuple(F(x) for x in p) for p in data["vertices"])
    edges = []
    for e in data["edges"]:
        if e["kind"] != "line":
            raise ValueError("Unexpected curve")
        a, b = e["vertices"]
        edges.append(Edge(a, b, Curve("line", vertices[a], vertices[b])))
    faces = []
    for f in data["faces"]:
        if f["kind"] != "plane":
            raise ValueError("Unexpected surface")
        faces.append(Face(Surface("plane", tuple(map(F, f["normal"])), F(f["offset"])),
                          tuple(tuple(Use(u["edge"], u["forward"]) for u in loop)
                                for loop in f["loops"])))
    result = Boundary(vertices, tuple(edges), tuple(faces), 0)
    if result.validate():
        raise ValueError(result.validate())
    return result


def volume(boundary):
    total = F(0)
    for face in boundary.faces:
        for loop in face.loops:
            points = [boundary.directed(u)[2].p0 for u in loop]
            total += sum((dot(points[0], cross(points[i], points[i+1])) / 6
                          for i in range(1, len(points)-1)), F(0))
    return total


def request(boundary, normal, offset):
    return {"schema_version": 1, "boundary": encode(boundary),
            "plane": {"normal": list(map(scalar, normal)), "offset": scalar(offset)}}


def execute(binary, payload):
    completed = subprocess.run([str(binary)], input=json.dumps(payload), text=True,
                               capture_output=True, timeout=30)
    if completed.returncode:
        raise ValueError(completed.stderr.strip())
    reply = json.loads(completed.stdout)
    boundary = decode(reply["boundary"])
    if F(reply["volume"]) != volume(boundary):
        raise ValueError("Rust volume disagrees with independent boundary measurement")
    return reply, boundary


def clip(binary, boundary, normal, offset):
    return execute(binary, request(boundary, normal, offset))


if __name__ == "__main__":
    # A reusable native shared-boundary fixture, not a mesh or vendor model.
    from adapters import from_planar
    from boundary import Body
    from kernel import Solid
    cube = from_planar(Body.from_solid(Solid.box((0, 0, 0), (2, 2, 2))))
    payload = request(cube, (1, 1, 1), F(3))
    (HERE / "fixtures" / "cube-oblique.request.json").write_text(json.dumps(payload, indent=2)+"\n")
