"""Uniform-density mass, SI conversion, exact geometry and read-only caching."""

from fractions import Fraction as F
import math
from pathlib import Path
import tempfile
import unittest
from measurements import measure_model, dispatch_measure
from store import CadError, Store
from test_intersection import rectangle, operations
from test_round_stock import cylinder
from test_analytic_measurements import exact_value
from test_polyhedral_transforms import moved, turned
from test_booleans import cases
from test_holes import perforated
from test_revolution import revolved


class MassProperties(unittest.TestCase):
    def measure(self, model, density=None):
        return measure_model(model, model["features"][-1]["id"], density)

    def test_box_mass_and_si_inertia_match_independent_closed_forms(self):
        result = self.measure(rectangle("box", 0, 0, 10, 4, 2), "1000/1")
        mass = result["mass_properties"]
        self.assertEqual(mass["density_kg_per_m3"], "1000")
        expected_mass = F(80 * 1000, 10**9)
        self.assertEqual(F(mass["mass_kg"]), expected_mass)
        lengths = [F(10, 1000), F(4, 1000), F(2, 1000)]
        expected = [
            expected_mass * sum(lengths[j] ** 2 for j in range(3) if j != i) / 12
            for i in range(3)
        ]
        self.assertEqual(
            [[F(v) for v in row] for row in mass["centroidal_inertia_kg_m2"]],
            [[expected[i] if i == j else F(0) for j in range(3)] for i in range(3)],
        )
        self.assertNotIn(
            "mass_properties", self.measure(rectangle("box", 0, 0, 10, 4, 2))
        )

    def test_cylinder_closed_forms_and_exact_rational_density(self):
        density = F(2345, 7)
        result = self.measure(cylinder(radius="5", height="12"), str(density))
        mass = result["mass_properties"]
        expected_mass = math.pi * 25 * 12 * float(density) / 10**9
        self.assertAlmostEqual(
            exact_value(mass["mass_kg"]), expected_mass, delta=expected_mass * 1e-14
        )
        radial = expected_mass * (3 * (5 / 1000) ** 2 + (12 / 1000) ** 2) / 12
        axial = expected_mass * (5 / 1000) ** 2 / 2
        for i, expected in enumerate([radial, radial, axial]):
            self.assertAlmostEqual(
                exact_value(mass["centroidal_inertia_kg_m2"][i][i]),
                expected,
                delta=expected * 1e-14,
            )
        self.assertIn("pi", mass["mass_kg"])

    def test_holes_revolutions_cavities_placements_and_geometry_reply_unchanged(self):
        models = [
            perforated(),
            revolved(),
            cases()["cavity"][0],
            cases()["separate"][0],
        ]
        for source in models:
            for model in [source, moved(source, (3, 5, 7)), turned(source, "z", 1)]:
                with self.subTest(feature=model["features"][-1]["kind"]):
                    original = self.measure(model)
                    result = self.measure(model, "3/7")
                    mass = result.pop("mass_properties")
                    self.assertEqual(result, original)
                    self.assertAlmostEqual(
                        exact_value(mass["mass_kg"]),
                        exact_value(original["volume_mm3"]) * 3 / (7 * 10**9),
                        delta=1e-15,
                    )
                    for i in range(3):
                        for j in range(3):
                            self.assertAlmostEqual(
                                exact_value(mass["centroidal_inertia_kg_m2"][i][j]),
                                exact_value(
                                    original["centroidal_volume_inertia_mm5"][i][j]
                                )
                                * 3
                                / (7 * 10**15),
                                delta=1e-18,
                            )

    def test_density_errors_revision_cache_separation_and_no_document_changes(self):
        model = rectangle("box", 0, 0, 10, 4, 2)
        for density, code in [
            ("0", "invalid_density"),
            ("-1", "invalid_density"),
            ("1/0", "invalid_number"),
            ("0.5", "invalid_number"),
            ("1000 kg/m3", "invalid_number"),
            (str(2**128), "invalid_number"),
        ]:
            with self.subTest(density=density), self.assertRaises(CadError) as caught:
                self.measure(model, density)
            self.assertEqual(caught.exception.detail["code"], code)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.json"
            store = Store(path)
            store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(model),
                    preserve=[],
                )
            )
            before = path.read_bytes()
            command = dict(expected_revision=1, feature_id=model["features"][-1]["id"])
            plain = dispatch_measure(store, command)["result"]
            one = dispatch_measure(store, {**command, "density_kg_per_m3": "1000"})[
                "result"
            ]
            two = dispatch_measure(store, {**command, "density_kg_per_m3": "2000"})[
                "result"
            ]
            self.assertEqual(
                F(two["mass_properties"]["mass_kg"]),
                2 * F(one["mass_properties"]["mass_kg"]),
            )
            self.assertEqual(dispatch_measure(store, command)["result"], plain)
            self.assertEqual(
                dispatch_measure(store, {**command, "density_kg_per_m3": None})[
                    "result"
                ],
                plain,
            )
            self.assertEqual(
                dispatch_measure(
                    store,
                    {**command, "expected_revision": 0, "density_kg_per_m3": "1000"},
                )["error"]["code"],
                "revision_conflict",
            )
            for density in (1000, True, {}, []):
                self.assertEqual(
                    dispatch_measure(store, {**command, "density_kg_per_m3": density})[
                        "error"
                    ]["code"],
                    "invalid_command",
                )
            self.assertEqual(path.read_bytes(), before)
