"""Exact tapered stock, editable parameters, supports and placed display boundary."""

from fractions import Fraction as F
import math
from pathlib import Path
import tempfile
import unittest
from store import CadError, Store, evaluate
from exports import tessellate
from topology import topology_model
from measurements import measure_model
from intent import explain_model
from test_holes import audit_triangles
from test_intersection import operations
from test_polyhedral_transforms import moved, turned, rotated
from test_instances import instance
from test_analytic_measurements import exact_value


def frustum(bottom="10", top="5", height="12"):
    return dict(
        parameters=dict(x="0", y="0", bottom=bottom, top=top, height=height),
        fixed={},
        features=[
            dict(
                kind="conical_frustum",
                id="taper",
                x="x",
                y="y",
                bottom_radius="bottom",
                top_radius="top",
                height="height",
            )
        ],
    )


class Frustum(unittest.TestCase):
    def test_exact_closed_forms_and_closed_tessellation(self):
        for r0, r1, h in [
            (F(10), F(5), F(12)),
            (F(5), F(10), F(12)),
            (F(7, 3), F(2, 5), F(11, 7)),
        ]:
            model = frustum(str(r0), str(r1), str(h))
            body = evaluate(model)["bodies"][0]
            coefficient = h * (r0 * r0 + r0 * r1 + r1 * r1) / 3
            self.assertEqual(
                body["analytic"]["volume"]["pi_subtract_mm3"], str(-coefficient)
            )
            values = measure_model(model, "taper")
            z = (
                h
                * (r0 * r0 + 2 * r0 * r1 + 3 * r1 * r1)
                / (4 * (r0 * r0 + r0 * r1 + r1 * r1))
            )
            self.assertEqual(values["centroid_mm"], ["0", "0", str(z)])
            izz = h * (r0**4 + r0**3 * r1 + r0**2 * r1**2 + r0 * r1**3 + r1**4) / 10
            szz = h**3 * (r0 * r0 + 3 * r0 * r1 + 6 * r1 * r1) / 30
            for pi in [F(2), F(3), F(22, 7)]:
                tensor = [
                    [exact_value(v, pi) for v in row]
                    for row in values["centroidal_volume_inertia_mm5"]
                ]
                self.assertEqual(
                    tensor,
                    [
                        [pi * (izz / 2 + szz - coefficient * z * z), 0, 0],
                        [0, pi * (izz / 2 + szz - coefficient * z * z), 0],
                        [0, 0, pi * izz],
                    ],
                )
            topology = topology_model(model, "taper")
            self.assertEqual(topology["shell_euler"], [2])
            self.assertEqual(len(topology["faces"]), 6)
            self.assertEqual(
                set(topology["surfaces"]),
                {
                    "feature/taper/cap/top",
                    "feature/taper/cap/bottom",
                    "feature/taper/outer/frustum",
                },
            )
            for segments in (16, 64, 256):
                mesh = tessellate(model, "taper", segments, True)
                triangles = [
                    [tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]
                ]
                volume = audit_triangles(triangles, 0)
                self.assertAlmostEqual(
                    volume,
                    float(coefficient) * segments * math.sin(math.tau / segments) / 2,
                    places=7,
                )
                self.assertEqual(
                    set(mesh["triangle_surfaces"]), set(topology["surfaces"])
                )
                self.assertAlmostEqual(
                    mesh["max_radial_error_mm"],
                    float(max(r0, r1)) * (1 - math.cos(math.pi / segments)),
                    places=12,
                )

    def test_placements_preserve_surface_names_and_rotate_moments(self):
        model = frustum()
        delta = (F(1, 3), F(-2, 5), F(7, 11))
        shifted = moved(model, delta)
        original = measure_model(shifted, "moved")
        original_tensor = original["centroidal_volume_inertia_mm5"]
        linked = instance(model, offset=delta)
        self.assertEqual(len(evaluate(linked)["bodies"]), 2)
        self.assertEqual(
            measure_model(linked, linked["features"][-1]["id"])[
                "centroidal_volume_inertia_mm5"
            ],
            original_tensor,
        )
        for axis in "xyz":
            for turns in (1, 2, 3):
                placed = turned(shifted, axis, turns)
                values = measure_model(placed, "turned")
                self.assertEqual(
                    list(map(F, values["centroid_mm"])),
                    list(
                        rotated(
                            list(map(F, original["centroid_mm"])),
                            axis,
                            turns,
                            (0, 0, 0),
                        )
                    ),
                )
                vectors = [
                    rotated(
                        tuple(int(i == j) for i in range(3)), axis, turns, (0, 0, 0)
                    )
                    for j in range(3)
                ]
                tensor = [
                    [exact_value(v, F(3)) for v in row] for row in original_tensor
                ]
                for i in range(3):
                    for j in range(3):
                        expected = sum(
                            vectors[a][i] * tensor[a][b] * vectors[b][j]
                            for a in range(3)
                            for b in range(3)
                        )
                        self.assertEqual(
                            exact_value(
                                values["centroidal_volume_inertia_mm5"][i][j], F(3)
                            ),
                            expected,
                        )
                topology = topology_model(placed, "turned")
                mesh = tessellate(placed, "turned", 32, True)
                support = topology["surfaces"]["feature/taper/outer/frustum"]
                for triangle, name in zip(mesh["triangles"], mesh["triangle_surfaces"]):
                    if name != "feature/taper/outer/frustum":
                        continue
                    for index in triangle:
                        d = [
                            p - float(F(o))
                            for p, o in zip(mesh["vertices"][index], support["origin"])
                        ]
                        z = sum(v * a for v, a in zip(d, support["axis"]))
                        radius = math.hypot(
                            *[v - z * a for v, a in zip(d, support["axis"])]
                        )
                        self.assertAlmostEqual(radius, 10 - 5 * z / 12, places=10)

    def test_validation_dependencies_and_atomic_reversible_edits(self):
        for key, value, code in [
            ("top", "0", "dimension_range"),
            ("top", "10", "invalid_taper"),
            ("bottom", "-1", "dimension_range"),
            ("height", "0", "dimension_range"),
        ]:
            model = frustum()
            model["parameters"][key] = value
            with self.assertRaises(CadError) as caught:
                evaluate(model)
            self.assertEqual(caught.exception.detail["code"], code)
        tiny = frustum(top=str(F(10) + F(1, 10**30)))
        evaluate(tiny)
        topology_model(tiny, "taper")
        measure_model(tiny, "taper")
        with self.assertRaises(CadError):
            tessellate(tiny, "taper")
        model = frustum()
        model["relations"] = {"top": dict(offset_mm="0", terms={"bottom": "1/2"})}
        changed = evaluate(model, [dict(op="set_parameter", id="bottom", mm="12")])
        self.assertEqual(changed["model"]["parameters"]["top"], "6")
        self.assertIn("top", explain_model(model, "taper")["parameters"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.json"
            store = Store(path)
            store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(frustum()),
                    preserve=[],
                )
            )
            before = path.read_bytes()
            proposal = dict(
                expected_revision=1,
                operations=[dict(op="set_parameter", id="top", mm="15")],
                preserve=[],
            )
            self.assertEqual(
                store.execute(dict(action="preview", **proposal))["bodies"][0][
                    "volume_mm3"
                ],
                "1900*pi",
            )
            self.assertEqual(path.read_bytes(), before)
            store.execute(dict(action="commit", transaction_id="widen", **proposal))
            self.assertEqual(
                Store(path).execute(dict(action="inspect"))["bodies"][0]["volume_mm3"],
                "1900*pi",
            )
            undone = store.execute(
                dict(action="undo", expected_revision=2, transaction_id="undo")
            )
            self.assertEqual(undone["bodies"][0]["volume_mm3"], "700*pi")


if __name__ == "__main__":
    unittest.main()
