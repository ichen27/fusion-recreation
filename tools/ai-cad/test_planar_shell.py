"""Uniform planar walls: independent closed forms and editable native history."""

from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest
from store import CadError, Store, evaluate
from topology import topology_model
from measurements import measure_model
from exports import tessellate
from test_holes import audit_triangles
from test_intersection import rectangle, prism, operations
from test_planar_loft import loft
from test_booleans import boolean, box
from test_frustum import frustum


def shell(model=None, thickness="2", opening=(0, 0, 1)):
    model = model or rectangle("part", 0, 0, 40, 30, 20)
    model["parameters"]["wall"] = thickness
    feature = dict(
        kind="planar_shell",
        id="shell",
        input=model["features"][-1]["id"],
        thickness="wall",
    )
    if opening is not None:
        feature["opening_normal"] = list(map(str, opening))
    model["features"].append(feature)
    return model


def box_expectation(opening=None, wall=F(2)):
    lo = [wall] * 3
    hi = [F(v) - wall for v in (40, 30, 20)]
    if opening:
        axis = next(i for i, v in enumerate(opening) if v)
        if opening[axis] > 0:
            hi[axis] = F((40, 30, 20)[axis])
        else:
            lo[axis] = F(0)
    inner = (hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2])
    volume = 24000 - inner
    center = [
        (24000 * F(size, 2) - inner * (a + b) / 2) / volume
        for size, a, b in zip((40, 30, 20), lo, hi)
    ]
    return volume, center


class PlanarShell(unittest.TestCase):
    def test_closed_and_all_six_openings_volume_centroid_topology_mesh(self):
        for opening in [
            None,
            (1, 0, 0),
            (-1, 0, 0),
            (0, 2, 0),
            (0, -3, 0),
            (0, 0, 4),
            (0, 0, -5),
        ]:
            with self.subTest(opening=opening):
                model = shell(opening=opening)
                volume, center = box_expectation(opening)
                self.assertEqual(F(evaluate(model)["bodies"][0]["volume_mm3"]), volume)
                self.assertEqual(
                    list(map(F, measure_model(model, "shell")["centroid_mm"])), center
                )
                topology = topology_model(model, "shell")
                self.assertEqual(len(topology["shells"]), 1 if opening else 2)
                mesh = tessellate(model, "shell", 32, True)
                self.assertAlmostEqual(
                    audit_triangles(
                        [
                            [tuple(mesh["vertices"][i]) for i in t]
                            for t in mesh["triangles"]
                        ],
                        0,
                        1 if opening else 2,
                    ),
                    float(volume),
                )

    def test_exact_slanted_walls_and_tiny_thickness(self):
        # Loft sides have a 5-12-13 normal. Offset is perpendicular, not axial.
        m = shell(loft(), "1", None)
        inner = F(10, 6) * (
            2 * 37 * 17 + 37 * F(26, 3) + F(86, 3) * 17 + 2 * F(86, 3) * F(26, 3)
        )
        self.assertEqual(F(evaluate(m)["bodies"][0]["volume_mm3"]), 6400 - inner)
        # 3-4-5 triangle at scale ten: its inradius is ten; inset area scales quadratically.
        m = shell(prism("part", [(0, 0), (40, 0), (0, 30)], 20), "2", None)
        self.assertEqual(
            F(evaluate(m)["bodies"][0]["volume_mm3"]),
            12000 - F(600) * F(8, 10) ** 2 * 16,
        )
        tiny = F(1, 10**30)
        self.assertEqual(
            F(evaluate(shell(thickness=str(tiny)))["bodies"][0]["volume_mm3"]),
            box_expectation((0, 0, 1), tiny)[0],
        )
        # An irrational face may be the opening: it is not offset.
        m = prism("part", [(0, 0), (20, 0), (0, 20)], 10)
        self.assertGreater(
            F(evaluate(shell(m, "1", (1, 1, 0)))["bodies"][0]["volume_mm3"]), 0
        )

    def test_invalid_offsets_openings_and_nonconvex_input_reject(self):
        cases = [
            (shell(thickness="0"), "dimension_range"),
            (shell(thickness="15"), "shell_thickness"),
            (shell(opening=(0, 0, 0)), "opening_normal"),
            (shell(opening=(1, 1, 1)), "missing_opening"),
            (shell(loft(height="10"), "1"), "unsupported_shell"),
        ]
        for m, code in cases:
            with self.subTest(code=code), self.assertRaises(CadError) as caught:
                evaluate(m)
            self.assertEqual(caught.exception.detail["code"], code)
        nested = shell(shell(), "1")
        nested["features"][-1]["id"] = "nested"
        for m in [
            nested,
            shell(frustum(), "1"),
            shell(prism("part", [(0, 0), (30, 0), (10, 10), (0, 30)], 20), "1"),
        ]:
            with self.assertRaises(CadError) as caught:
                evaluate(m)
            self.assertIn(
                caught.exception.detail["code"],
                ("unsupported_reference", "unsupported_profile"),
            )

    def test_downstream_boolean_and_plane_cut_preserve_hollow_material(self):
        # A square drain removes only the two-mm floor, not the empty interior.
        m = boolean(shell(), box("drain", [10, 10, -1], [15, 15, 21]), "difference")
        self.assertEqual(evaluate(m)["bodies"][0]["volume_mm3"], "7102")
        topology_model(m, "result")
        m = shell(opening=None)
        m["parameters"]["cut_z"] = "10"
        m["features"].append(
            dict(
                kind="plane_cut",
                id="cut",
                input="shell",
                normal=["0", "0", "1"],
                offset="cut_z",
            )
        )
        self.assertEqual(evaluate(m)["bodies"][0]["volume_mm3"], "4512")
        self.assertEqual(len(topology_model(m, "cut")["shells"]), 1)

    def test_history_upstream_edits_constraints_and_atomic_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "part.json")
            made = store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(shell()),
                    preserve=[],
                )
            )
            original = store.path.read_bytes()
            edit = dict(
                expected_revision=1,
                operations=[dict(op="set_parameter", id="wall", mm="3")],
                preserve=[],
            )
            preview = store.execute(dict(action="preview", **edit))
            self.assertEqual(
                F(preview["bodies"][0]["volume_mm3"]),
                box_expectation((0, 0, 1), F(3))[0],
            )
            self.assertEqual(store.path.read_bytes(), original)
            store.execute(dict(action="commit", transaction_id="thicker", **edit))
            saved = store.path.read_bytes()
            with self.assertRaises(CadError):
                store.execute(
                    dict(
                        action="commit",
                        expected_revision=2,
                        transaction_id="invalid",
                        operations=[dict(op="set_parameter", id="wall", mm="20")],
                        preserve=[],
                    )
                )
            self.assertEqual(store.path.read_bytes(), saved)
            self.assertEqual(
                Store(store.path).execute(
                    dict(action="undo", expected_revision=2, transaction_id="undo")
                )["bodies"],
                made["bodies"],
            )
        m = shell()
        m["parameters"]["base"] = "1"
        m["relations"] = {"wall": dict(offset_mm="0", terms={"base": "2"})}
        self.assertEqual(
            F(
                evaluate(m, [dict(op="set_parameter", id="base", mm="3/2")])["bodies"][
                    0
                ]["volume_mm3"]
            ),
            box_expectation((0, 0, 1), F(3))[0],
        )
        with self.assertRaises(CadError):
            evaluate(m, [dict(op="set_parameter", id="wall", mm="3")])
        m = shell()
        self.assertNotEqual(
            evaluate(m, [dict(op="set_parameter", id="part.height", mm="25")])[
                "bodies"
            ],
            evaluate(m)["bodies"],
        )
        with self.assertRaises(CadError):
            evaluate(m, [dict(op="remove_parameter", id="wall")])
