"""End-to-end Rust checks against shared topology and exact independent invariants."""
import copy
from fractions import Fraction as F
import json
from pathlib import Path
import random
import subprocess
import sys
import unittest

from bridge import HERE, clip, decode, encode, execute, request, volume
from adapters import from_planar, from_curved
from topology import Curve, Patch, Surface, build
from boundary import Body
from kernel import Solid, clip as reference_clip, volume as reference_volume
from curves import Disk
from cylinders import Body as Curved

BINARY = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "target/release/boundary-clip"


def topology(solid):
    return from_planar(Body.from_solid(solid))


class ClippingTests(unittest.TestCase):
    def setUp(self):
        self.cube = topology(Solid.box((0, 0, 0), (2, 2, 2)))

    def assertRejected(self, payload):
        process = subprocess.run([str(BINARY)], input=json.dumps(payload), text=True,
                                 capture_output=True, timeout=30)
        self.assertEqual(process.returncode, 2, process.stdout + process.stderr)
        self.assertEqual(process.stdout, "")
        self.assertTrue(json.loads(process.stderr)["error"])

    def test_analytic_box_and_corner_tetrahedron(self):
        for normal, offset, expected in [((1, 0, 0), F(1, 3), F(4, 3)),
                                         ((1, 1, 1), 1, F(1, 6)),
                                         ((1, 1, 1), 3, 4)]:
            reply, boundary = clip(BINARY, self.cube, normal, offset)
            self.assertEqual(F(reply["volume"]), expected)
            self.assertEqual(boundary.summary()["shell_euler"], [2])

    def test_contacts_empty_and_unchanged(self):
        for normal, offset in [((1, 0, 0), 0), ((1, 1, 0), 0), ((1, 1, 1), 0), ((1, 0, 0), -1)]:
            reply, result = clip(BINARY, self.cube, normal, offset)
            self.assertEqual(reply["classification"], "empty")
            self.assertEqual(result.summary()["vertices"], 0)
        for offset in (2, 3):
            reply, result = clip(BINARY, self.cube, (1, 0, 0), offset)
            self.assertEqual(reply["classification"], "unchanged")
            self.assertEqual(volume(result), 8)

    def test_plane_through_existing_vertices_and_edges(self):
        for normal, offset in [((1, 1, 0), 2), ((1, -1, 0), 0), ((1, 1, 1), 2), ((1, 1, 1), 4)]:
            a, _ = clip(BINARY, self.cube, normal, offset)
            b, _ = clip(BINARY, self.cube, tuple(-x for x in normal), -offset)
            self.assertEqual(F(a["volume"]) + F(b["volume"]), 8)

    def test_exact_thin_and_large_translated_solids(self):
        thin = topology(Solid.box((0, 0, 0), (1, 1, F(1, 10**30))))
        reply, _ = clip(BINARY, thin, (0, 0, 1), F(1, 2*10**30))
        self.assertEqual(F(reply["volume"]), F(1, 2*10**30))
        big = 10**30
        shifted = topology(Solid.box((big, big, big), (big+2, big+2, big+2)))
        reply, _ = clip(BINARY, shifted, (1, 1, 1), 3*big+1)
        self.assertEqual(F(reply["volume"]), F(1, 6))

    def test_random_splits_reference_and_conservation(self):
        rng = random.Random(20261015)
        for i in range(40):
            # Rational rotation, shear, translation and reflected input orientation.
            matrix = ((F(3, 5), F(-4, 5), F(1, 7)),
                      (F(4, 5), F(3, 5), 0), (0, 0, -1 if i % 2 else 1))
            solid = Solid.box((-1, -1, -1), (1, 1, 1)).affine(
                matrix, (F(i, 7), F(-i, 11), F(i, 13)))
            boundary = topology(solid)
            normal = tuple(F(rng.randint(-3, 3)) for _ in range(3))
            if normal == (0, 0, 0): normal = (F(1), F(0), F(0))
            center = (F(i, 7), F(-i, 11), F(i, 13))
            offset = sum(n*x for n, x in zip(normal, center)) + F(rng.randint(-3, 3), 4)
            with self.subTest(case=i):
                reply, result = clip(BINARY, boundary, normal, offset)
                complement, _ = clip(BINARY, boundary, tuple(-x for x in normal), -offset)
                self.assertEqual(F(reply["volume"]) + F(complement["volume"]), volume(boundary))
                self.assertEqual(volume(result), reference_volume(reference_clip(solid, normal, offset)))
                repeat, _ = clip(BINARY, result, normal, offset)
                self.assertEqual(reply["boundary"], repeat["boundary"])
                # Positive rescaling must not change the represented half-space.
                scaled, _ = clip(BINARY, boundary, tuple(3*x for x in normal), 3*offset)
                self.assertEqual(scaled["volume"], reply["volume"])

    def test_repeated_cuts_and_order_independence(self):
        a, b = self.cube, self.cube
        planes = [((1, 1, 1), F(4)), ((-1, 0, 1), F(1)), ((0, 1, 0), F(3, 2))]
        for n, d in planes: _, a = clip(BINARY, a, n, d)
        for n, d in reversed(planes): _, b = clip(BINARY, b, n, d)
        self.assertEqual(volume(a), volume(b))
        self.assertEqual(set(a.vertices), set(b.vertices))

    def test_subdivided_edges_and_coplanar_faces(self):
        patches = []
        for i, face in enumerate(self.cube.faces):
            curves = tuple(self.cube.directed(u)[2] for u in face.loops[0])
            if i == 0:
                pts = [c.p0 for c in curves]
                for indices in ((0, 1, 2), (0, 2, 3)):
                    triangle = [pts[k] for k in indices]
                    edges = tuple(Curve("line", p, triangle[(j+1) % 3]) for j, p in enumerate(triangle))
                    patches.append(Patch(face.surface, (edges,)))
            else:
                mid = curves[0].point(F(1, 2))
                subdivided = (Curve("line", curves[0].p0, mid), Curve("line", mid, curves[0].p1)) + curves[1:]
                patches.append(Patch(face.surface, (subdivided,)))
        boundary = build(patches)
        _, result = clip(BINARY, boundary, (1, 1, 1), 3)
        self.assertEqual(volume(result), 4)

    def test_saved_fixture_and_roundtrip(self):
        payload = json.loads((HERE / "fixtures/cube-oblique.request.json").read_text())
        reply, result = execute(BINARY, payload)
        expected = json.loads((HERE / "fixtures/cube-oblique.reply.json").read_text())
        self.assertEqual(reply, expected)
        self.assertEqual(encode(decode(reply["boundary"])), reply["boundary"])
        self.assertEqual(volume(result), 4)

    def test_empty_input(self):
        _, empty = clip(BINARY, self.cube, (1, 0, 0), -1)
        reply, _ = clip(BINARY, empty, (1, 0, 0), 0)
        self.assertEqual(reply["classification"], "empty")

    def test_broken_incidence_and_geometry_rejected(self):
        base = request(self.cube, (1, 0, 0), 1)
        mutations = [
            lambda b: b["faces"].pop(),
            lambda b: b["faces"].append(copy.deepcopy(b["faces"][0])),
            lambda b: b["edges"][0]["vertices"].__setitem__(0, 999),
            lambda b: b["faces"][0]["loops"][0][0].__setitem__("edge", 999),
            lambda b: b["faces"][0]["loops"][0][0].__setitem__(
                "forward", not b["faces"][0]["loops"][0][0]["forward"]),
            lambda b: b["faces"][0].__setitem__("offset", "99"),
            lambda b: b["vertices"].append(["3", "4", "5"]),
            lambda b: b["vertices"].__setitem__(0, list(b["vertices"][1])),
            lambda b: b["faces"][0].__setitem__("normal", ["0", "0", "0"]),
            lambda b: b["faces"][0]["loops"][0].reverse(),
        ]
        for i, mutate in enumerate(mutations):
            payload = copy.deepcopy(base)
            mutate(payload["boundary"])
            with self.subTest(mutation=i): self.assertRejected(payload)

    def test_nonconvex_and_cavity_rejected(self):
        box = Body.from_solid(Solid.box((0, 0, 0), (3, 3, 3)))
        for tool in [Solid.box((1, 1, 1), (2, 2, 2)), Solid.box((1, 1, -1), (4, 4, 4))]:
            boundary = from_planar(box.cut(Body.from_solid(tool)))
            self.assertRejected(request(boundary, (1, 0, 0), 2))

    def test_curves_and_face_holes_rejected(self):
        with self.assertRaises(ValueError): encode(from_curved(Curved.extrude(Disk(0, 0, 1), 0, 2)))
        base = request(self.cube, (1, 0, 0), 1)
        for change in ("edge", "face", "hole"):
            payload = copy.deepcopy(base)
            if change == "edge": payload["boundary"]["edges"][0]["kind"] = "arc"
            elif change == "face": payload["boundary"]["faces"][0]["kind"] = "cylinder"
            else: payload["boundary"]["faces"][0]["loops"].append([])
            self.assertRejected(payload)

    def test_bad_protocol_numbers_and_limits(self):
        base = request(self.cube, (1, 0, 0), 1)
        for value in ("1/0", "NaN", "1.0", "1e30", "9"*400, 1.5):
            payload = copy.deepcopy(base)
            payload["plane"]["offset"] = value
            self.assertRejected(payload)
        for key, value in (("schema_version", 2), ("unexpected", True)):
            payload = copy.deepcopy(base)
            payload[key] = value
            self.assertRejected(payload)
        payload = copy.deepcopy(base)
        payload["plane"]["normal"] = ["0", "0", "0"]
        self.assertRejected(payload)
        payload = copy.deepcopy(base)
        payload["boundary"]["vertices"] *= 17
        self.assertRejected(payload)
        self.assertRejected({"oversized": "x" * 1_048_576})

    def test_deterministic_and_input_unchanged(self):
        payload = request(self.cube, (1, 1, 1), 3)
        before = copy.deepcopy(payload)
        first, _ = execute(BINARY, payload)
        second, _ = execute(BINARY, payload)
        self.assertEqual(first, second)
        self.assertEqual(payload, before)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ClippingTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
