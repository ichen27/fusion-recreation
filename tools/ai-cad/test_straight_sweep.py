"""Exact affine prism geometry, moments, edit history and downstream operations."""

import copy
from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest
from store import CadError, Store, evaluate
from exports import tessellate
from topology import topology_model
from measurements import measure_model
from test_holes import audit_triangles
from test_profiles import model_for
from test_intersection import operations
from test_instances import instance
from test_polyhedral_transforms import moved, turned


def swept(points=None, offset=(7, -3, 12), reverse=False):
    m = model_for(points or [(0, 0), (40, 0), (40, 20), (0, 20)], "1", reverse)
    m["features"][0]["kind"] = "planar_profile"
    m["parameters"].update({f"sweep.{a}": str(v) for a, v in zip("xyz", offset)})
    m["features"][-1] = dict(
        kind="straight_sweep",
        id="part",
        profile="outline",
        offset=[f"sweep.{a}" for a in "xyz"],
    )
    return m


class StraightSweep(unittest.TestCase):
    def test_rectangle_volume_centroid_tensor_and_outward_mesh(self):
        for delta in [(7, -3, 12), (0, 0, -12), (F(1, 3), F(-2, 7), F(-3, 5))]:
            for reverse in (False, True):
                m = swept(offset=delta, reverse=reverse)
                volume = 800 * abs(F(delta[2]))
                self.assertEqual(F(evaluate(m)["bodies"][0]["volume_mm3"]), volume)
                values = measure_model(m, "part")
                self.assertEqual(
                    list(map(F, values["centroid_mm"])),
                    [F(20) + F(delta[0]) / 2, F(10) + F(delta[1]) / 2, F(delta[2]) / 2],
                )
                cov = [
                    [
                        F(delta[i]) * F(delta[j]) / 12
                        + (F([1600, 400, 0][i], 12) if i == j else 0)
                        for j in range(3)
                    ]
                    for i in range(3)
                ]
                trace = sum(cov[i][i] for i in range(3))
                expected = [
                    [volume * ((trace if i == j else 0) - cov[i][j]) for j in range(3)]
                    for i in range(3)
                ]
                self.assertEqual(
                    [
                        [F(v) for v in row]
                        for row in values["centroidal_volume_inertia_mm5"]
                    ],
                    expected,
                )
                top = topology_model(m, "part")
                self.assertEqual(len(top["faces"]), 6)
                mesh = tessellate(m, "part", 32, True)
                triangles = [
                    [tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]
                ]
                self.assertAlmostEqual(
                    audit_triangles(triangles, 0), float(volume), places=7
                )
                self.assertTrue(
                    all(s in top["surfaces"] for s in mesh["triangle_surfaces"])
                )

    def test_concave_profile_cut_and_linked_transforms(self):
        m = swept([(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)], (7, -3, 12))
        self.assertEqual(evaluate(m)["bodies"][0]["volume_mm3"], "768")
        for model in [
            moved(m, (1, 2, 3)),
            turned(m, "x", 1),
            instance(m, offset=(50, 0, 0)),
        ]:
            for body in evaluate(model)["bodies"]:
                self.assertEqual(body["volume_mm3"], "768")
                topology_model(model, body["feature_id"])
        m["parameters"]["half"] = "6"
        m["features"].append(
            dict(
                kind="plane_cut",
                id="cut",
                input="part",
                normal=["0", "0", "1"],
                offset="half",
            )
        )
        self.assertEqual(evaluate(m)["bodies"][0]["volume_mm3"], "384")

    def test_invalid_direction_range_reference_and_small_exact_height(self):
        cases = [
            (swept(offset=(7, 3, 0)), "sweep_direction"),
            (swept(offset=(1000000, 0, 1)), "coordinate_range"),
            (swept(offset=(0, 0, 1000001)), "coordinate_range"),
        ]
        bad = swept()
        bad["features"][-1]["profile"] = "part"
        cases.append((bad, "unsupported_reference"))
        for m, code in cases:
            with self.assertRaises(CadError) as caught:
                evaluate(m)
            self.assertEqual(caught.exception.detail["code"], code)
        m = swept(offset=(F(1, 3), F(1, 7), F(1, 10**30)))
        self.assertEqual(F(evaluate(m)["bodies"][0]["volume_mm3"]), F(800, 10**30))
        topology_model(m, "part")

    def test_source_relations_fixed_parameters_and_atomic_reopen_undo(self):
        m = swept(offset=(6, -3, 12))
        m["relations"] = {"sweep.x": dict(offset_mm="0", terms={"sweep.z": "1/2"})}
        linked = instance(m, offset=(50, 0, 0))
        changed = evaluate(linked, [dict(op="set_parameter", id="sweep.z", mm="24")])
        self.assertEqual(changed["model"]["parameters"]["sweep.x"], "12")
        self.assertTrue(all(b["volume_mm3"] == "19200" for b in changed["bodies"]))
        frozen = copy.deepcopy(m)
        frozen["fixed"] = {"sweep.z": "12"}
        with self.assertRaises(CadError):
            evaluate(frozen, [dict(op="set_parameter", id="sweep.z", mm="24")])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.json"
            store = Store(path)
            created = store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(m),
                    preserve=[],
                )
            )
            before = path.read_bytes()
            edit = dict(
                expected_revision=1,
                operations=[dict(op="set_parameter", id="sweep.z", mm="24")],
                preserve=[],
            )
            preview = store.execute(dict(action="preview", **edit))
            self.assertEqual(preview["bodies"][0]["volume_mm3"], "19200")
            self.assertEqual(path.read_bytes(), before)
            store.execute(dict(action="commit", transaction_id="edit", **edit))
            saved = path.read_bytes()
            with self.assertRaises(CadError):
                store.execute(
                    dict(
                        action="commit",
                        expected_revision=2,
                        transaction_id="invalid",
                        operations=[dict(op="set_parameter", id="sweep.z", mm="0")],
                        preserve=[],
                    )
                )
            self.assertEqual(path.read_bytes(), saved)
            self.assertEqual(
                Store(path).execute(
                    dict(action="undo", expected_revision=2, transaction_id="undo")
                )["bodies"],
                created["bodies"],
            )
