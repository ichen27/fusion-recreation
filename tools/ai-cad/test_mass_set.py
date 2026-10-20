"""Independent rigid-body sums, signs, mixed densities, limits and transport."""

from fractions import Fraction as F
import json
import math
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
from engine_transport import NativeWorker
from mass_properties import measure_mass_set, dispatch_mass_set
from measurements import measure_model
from store import BINARY, CadError, Store, encode
from test_intersection import rectangle, operations
from test_interference import pair
from test_instances import instance
from test_round_stock import cylinder
from test_analytic_measurements import exact_value


def source(offset=(20, 30, 40)):
    return instance(rectangle("box", 0, 0, 10, 4, 2), offset=offset)


def parts(a="1000", b="2000"):
    return [
        dict(feature_id="box", density_kg_per_m3=a),
        dict(feature_id="copy", density_kg_per_m3=b),
    ]


def independent(masses, centers, own):
    total = sum(masses)
    center = [sum(m * c[i] for m, c in zip(masses, centers)) / total for i in range(3)]
    tensor = [[0 for _ in range(3)] for _ in range(3)]
    for mass, point, inertia in zip(masses, centers, own):
        d = [(point[i] - center[i]) / 1000 for i in range(3)]
        for i in range(3):
            for j in range(3):
                tensor[i][j] += inertia[i][j] + mass * (
                    sum(d[k] ** 2 for k in range(3) if k != i)
                    if i == j
                    else -d[i] * d[j]
                )
    return total, center, tensor


class MassSet(unittest.TestCase):
    def test_exact_parallel_axis_formula_seeded_and_canonical_order(self):
        rng = random.Random(13071)
        for _ in range(24):
            offset = [F(rng.randint(-100, 100), rng.randint(1, 9)) for _ in range(3)]
            densities = [F(rng.randint(1, 9000), rng.randint(1, 9)) for _ in range(2)]
            model = source(offset)
            selected = parts(*(str(v) for v in densities))
            result = measure_mass_set(model, selected)
            self.assertEqual(result, measure_mass_set(model, selected[::-1]))
            masses = [F(80, 10**9) * d for d in densities]
            centers = [
                [F(5), F(2), F(1)],
                [F(5) + offset[0], F(2) + offset[1], F(1) + offset[2]],
            ]
            sides = [F(10, 1000), F(4, 1000), F(2, 1000)]
            own = [
                [
                    [
                        m * sum(sides[k] ** 2 for k in range(3) if k != i) / 12
                        if i == j
                        else F(0)
                        for j in range(3)
                    ]
                    for i in range(3)
                ]
                for m in masses
            ]
            mass, center, tensor = independent(masses, centers, own)
            self.assertEqual(F(result["mass_kg"]), mass)
            self.assertEqual(list(map(F, result["center_of_mass_mm"])), center)
            self.assertEqual(
                [[F(v) for v in row] for row in result["centroidal_inertia_kg_m2"]],
                tensor,
            )
            self.assertEqual(result["overlap_policy"], "count_each_selected_occurrence")

    def test_mixed_planar_curved_density_and_single_part_identity(self):
        model = pair(
            rectangle("box", 0, 0, 10, 4, 2),
            cylinder(cx="30", cy="20", radius="5", height="12"),
        )
        selected = [parts()[0], dict(feature_id="stock", density_kg_per_m3="2000")]
        result = measure_mass_set(model, selected)
        mb = 80 * 1000 / 10**9
        mc = math.pi * 25 * 12 * 2000 / 10**9
        centers = [[5.0, 2.0, 1.0], [30.0, 20.0, 6.0]]
        ib = [
            mb * (4**2 + 2**2) / 12e6,
            mb * (10**2 + 2**2) / 12e6,
            mb * (10**2 + 4**2) / 12e6,
        ]
        ic = [mc * (3 * 5**2 + 12**2) / 12e6] * 2 + [mc * 5**2 / 2e6]
        own = [
            [[diagonal[i] if i == j else 0.0 for j in range(3)] for i in range(3)]
            for diagonal in [ib, ic]
        ]
        mass, center, tensor = independent([mb, mc], centers, own)
        self.assertAlmostEqual(exact_value(result["mass_kg"]), mass, delta=mass * 1e-13)
        for i in range(3):
            self.assertAlmostEqual(
                exact_value(result["center_of_mass_mm"][i]), center[i], delta=1e-12
            )
            for j in range(3):
                self.assertAlmostEqual(
                    exact_value(result["centroidal_inertia_kg_m2"][i][j]),
                    tensor[i][j],
                    delta=1e-17,
                )
        for part in selected:
            one = measure_mass_set(model, [part])
            measured = measure_model(
                model, part["feature_id"], part["density_kg_per_m3"]
            )
            self.assertEqual(one["mass_kg"], measured["mass_properties"]["mass_kg"])
            self.assertEqual(one["center_of_mass_mm"], measured["centroid_mm"])
            self.assertEqual(
                one["centroidal_inertia_kg_m2"],
                measured["mass_properties"]["centroidal_inertia_kg_m2"],
            )

    def test_overlap_is_additive_and_placement_invariant(self):
        result = measure_mass_set(source((0, 0, 0)), parts())
        one = measure_model(source(), "box", "3000")["mass_properties"]
        self.assertEqual(result["mass_kg"], one["mass_kg"])
        self.assertEqual(
            result["centroidal_inertia_kg_m2"], one["centroidal_inertia_kg_m2"]
        )
        original = source()
        moved = instance(
            instance(original, "box", "a", (10000, -30000, 5000)),
            "copy",
            "b",
            (10000, -30000, 5000),
        )
        a = measure_mass_set(original, parts())
        b = measure_mass_set(
            moved,
            [
                dict(feature_id="a", density_kg_per_m3="1000"),
                dict(feature_id="b", density_kg_per_m3="2000"),
            ],
        )
        self.assertEqual(a["centroidal_inertia_kg_m2"], b["centroidal_inertia_kg_m2"])
        self.assertEqual(
            [
                F(b["center_of_mass_mm"][i]) - F(a["center_of_mass_mm"][i])
                for i in range(3)
            ],
            [10000, -30000, 5000],
        )

    def test_sixteen_occurrences_and_shared_dimension_edit(self):
        model = rectangle("box", 0, 0, 10, 4, 2)
        selected = [dict(feature_id="box", density_kg_per_m3="1000")]
        for i in range(1, 16):
            model = instance(model, "box", f"copy{i}", (i * 20, 0, 0))
            selected.append(dict(feature_id=f"copy{i}", density_kg_per_m3="1000"))
        before = measure_mass_set(model, selected)
        self.assertEqual(F(before["mass_kg"]), F(16, 12500))
        self.assertEqual(before["center_of_mass_mm"], ["155", "2", "1"])
        height = model["features"][1]["height"]
        model["parameters"][height] = "4"
        after = measure_mass_set(model, selected)
        self.assertEqual(F(after["mass_kg"]), 2 * F(before["mass_kg"]))
        self.assertEqual(after["center_of_mass_mm"], ["155", "2", "2"])

    def test_errors_are_atomic_and_cache_revision_and_worker_match(self):
        model = source()
        for selection, code in [
            ([], "mass_limit"),
            (parts() * 9, "mass_limit"),
            ([parts()[0]] * 2, "duplicate_id"),
            ([dict(feature_id="missing", density_kg_per_m3="1")], "missing_body"),
            ([dict(feature_id="box.profile", density_kg_per_m3="1")], "missing_body"),
            (parts("0"), "invalid_density"),
            (parts("-1"), "invalid_density"),
            (parts("0.5"), "invalid_number"),
        ]:
            with self.subTest(code=code), self.assertRaises(CadError) as caught:
                measure_mass_set(model, selection)
            self.assertEqual(caught.exception.detail["code"], code)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.cad.json"
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
            command = dict(expected_revision=1, parts=parts())
            a = dispatch_mass_set(store, command)
            b = dispatch_mass_set(store, {**command, "parts": parts("2000", "4000")})
            self.assertEqual(F(b["result"]["mass_kg"]), 2 * F(a["result"]["mass_kg"]))
            self.assertEqual(dispatch_mass_set(store, command), a)
            self.assertEqual(
                dispatch_mass_set(store, {**command, "expected_revision": 0})["error"][
                    "code"
                ],
                "revision_conflict",
            )
            for invalid in [
                None,
                {},
                [],
                [{}],
                [dict(feature_id="box", density_kg_per_m3=1000)],
            ]:
                self.assertEqual(
                    dispatch_mass_set(store, {**command, "parts": invalid})["error"][
                        "code"
                    ],
                    "invalid_command",
                )
            self.assertEqual(path.read_bytes(), before)
        worker = NativeWorker()
        self.addCleanup(worker.close)
        data = encode(dict(model=model, parts=parts()))
        fresh = subprocess.run(
            [str(BINARY), "--mass-set"], input=data, capture_output=True, check=True
        )
        self.assertEqual(
            json.loads(fresh.stdout),
            json.loads(worker.run(BINARY, "--mass-set", data).stdout),
        )
        self.assertEqual(worker.run(BINARY, "--mass-set", b"{}").returncode, 1)
        self.assertEqual(worker.run(BINARY, "--mass-set", data).returncode, 0)
