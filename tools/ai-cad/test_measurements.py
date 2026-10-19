"""Exact volume integrals, transform covariance, topology and read-only revision checks."""

from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest
from measurements import measure_model, dispatch_measure
from store import Store, CadError
from test_intersection import rectangle, operations
from test_concave_operations import l_shape
from test_booleans import cases
from test_polyhedral_transforms import moved, turned
from test_instances import instance
from test_plane_cuts import tetra


def measure(model, feature=None):
    return measure_model(model, feature or model["features"][-1]["id"])


class Measurements(unittest.TestCase):
    def test_box_and_shifted_tetrahedron_closed_forms(self):
        box = measure(rectangle("box", 0, 0, 10, 4, 2))
        self.assertEqual(box["centroid_mm"], ["5", "2", "1"])
        self.assertEqual(box["bounds_mm"], [["0", "0", "0"], ["10", "4", "2"]])
        self.assertEqual(
            box["centroidal_volume_inertia_mm5"],
            [["400/3", "0", "0"], ["0", "2080/3", "0"], ["0", "0", "2320/3"]],
        )
        t = measure(tetra())  # vertices (10,0,0),(60,0,0),(10,50,0),(10,0,50)
        self.assertEqual(t["centroid_mm"], ["45/2", "25/2", "25/2"])
        volume = F(50**3, 6)
        inertia = [[F(v) for v in row] for row in t["centroidal_volume_inertia_mm5"]]
        for i in range(3):
            for j in range(3):
                self.assertEqual(
                    inertia[i][j],
                    volume * 2500 * F(3 if i == j else 1, 40 if i == j else 80),
                )

    def test_concave_winding_cavity_and_separated_components(self):
        a, b = measure(l_shape()), measure(l_shape(True))
        for k in a:
            self.assertEqual(a[k], b[k])
        self.assertEqual(a["centroid_mm"], ["121/34", "121/34", "2"])
        cavity = measure(cases()["cavity"][0])
        self.assertEqual(cavity["centroid_mm"], ["5"] * 3)
        expected = (F(1000) * 100 - F(216) * 36) / 6
        self.assertEqual(
            cavity["centroidal_volume_inertia_mm5"],
            [[str(expected if i == j else 0) for j in range(3)] for i in range(3)],
        )
        self.assertEqual(
            measure(cases()["separate"][0])["centroid_mm"], ["15", "5", "5"]
        )
        separate = measure(cases()["separate"][0])
        self.assertEqual(
            separate["centroidal_volume_inertia_mm5"],
            [["100000/3", "0", "0"], ["0", "700000/3", "0"], ["0", "0", "700000/3"]],
        )
        self.assertEqual(measure(cases()["through"][0])["centroid_mm"], ["5"] * 3)

    def test_translation_invariance_and_rotation_tensor_covariance(self):
        source = l_shape()
        original = measure(source)
        delta = (F(7, 3), F(-2, 5), F(11, 7))
        for placed in [moved(source, delta), instance(source, offset=delta)]:
            result = measure(placed)
            self.assertEqual(
                result["centroid_mm"],
                [str(F(c) + d) for c, d in zip(original["centroid_mm"], delta)],
            )
            self.assertEqual(
                result["centroidal_volume_inertia_mm5"],
                original["centroidal_volume_inertia_mm5"],
            )
        inertia = original["centroidal_volume_inertia_mm5"]
        rotated = measure(turned(source, "z", 1))
        self.assertEqual(
            rotated["centroid_mm"],
            [str(-F(original["centroid_mm"][1])), original["centroid_mm"][0], "2"],
        )
        # R I R^T for a right-handed Z quarter turn.
        order, signs = [1, 0, 2], [-1, 1, 1]
        self.assertEqual(
            rotated["centroidal_volume_inertia_mm5"],
            [
                [
                    str(F(inertia[order[i]][order[j]]) * signs[i] * signs[j])
                    for j in range(3)
                ]
                for i in range(3)
            ],
        )

    def test_read_only_history_revision_and_unsupported_stock(self):
        model = instance(l_shape())
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "part.json")
            store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(model),
                    preserve=[],
                )
            )
            before = store.path.read_bytes()
            command = dict(expected_revision=1, feature_id="copy")
            reply = dispatch_measure(store, command)
            self.assertEqual(reply["result"]["volume_mm3"], "204")
            self.assertEqual(dispatch_measure(store, command), reply)
            for args, code in [
                (dict(expected_revision=0, feature_id="copy"), "revision_conflict"),
                (dict(expected_revision=True, feature_id="copy"), "revision_conflict"),
                (dict(expected_revision=1, feature_id="missing"), "missing_body"),
                ([], "invalid_command"),
            ]:
                self.assertEqual(dispatch_measure(store, args)["error"]["code"], code)
            self.assertEqual(store.path.read_bytes(), before)
        from test_round_stock import flange

        with self.assertRaises(CadError) as error:
            measure(flange())
        self.assertEqual(error.exception.detail["code"], "unsupported_measurement")


if __name__ == "__main__":
    unittest.main()
