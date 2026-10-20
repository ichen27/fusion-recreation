"""Persistent original-engine materials, inheritance, conflict and exact mass."""

import copy
from pathlib import Path
import tempfile
import unittest
from materials import dispatch_material_mass
from store import evaluate, Store, CadError
from test_booleans import box, boolean
from test_instances import instance
from test_intersection import operations


def assign(feature, name="Test material", density="1000"):
    return dict(
        op="set_material",
        feature_id=feature,
        material=dict(name=name, density_kg_per_m3=density),
    )


def model():
    return instance(box("part", [0, 0, 0], [10, 4, 2]), name="copy", offset=(20, 0, 0))


class Materials(unittest.TestCase):
    def test_original_outputs_and_source_copy_inheritance(self):
        m = model()
        old = evaluate(m)
        self.assertNotIn("materials", old["model"])
        self.assertNotIn("resolved_materials", old)
        result = evaluate(m, [assign("part", density="2000/2")])
        self.assertEqual(result["bodies"], old["bodies"])
        self.assertEqual(
            result["model"]["materials"]["part"]["density_kg_per_m3"], "1000"
        )
        for feature in ("part", "copy"):
            self.assertEqual(
                result["resolved_materials"][feature]["source_features"], ["part"]
            )
        overridden = evaluate(result["model"], [assign("copy", "Other", "2000")])
        changed = evaluate(overridden["model"], [assign("part", density="3000")])
        self.assertEqual(
            changed["resolved_materials"]["copy"]["material"]["density_kg_per_m3"],
            "2000",
        )
        restored = evaluate(
            changed["model"], [dict(op="clear_material", feature_id="copy")]
        )
        self.assertEqual(
            restored["resolved_materials"]["copy"]["material"]["density_kg_per_m3"],
            "3000",
        )

    def test_boolean_conflicts_difference_and_explicit_uniform_override(self):
        a = box("a", [0, 0, 0], [10, 10, 10])
        b = box("b", [5, 0, 0], [15, 10, 10])
        for operation in ["union", "intersection", "difference"]:
            m = boolean(a, b, operation)
            result = evaluate(m, [assign("a"), assign("b", "Other", "2000")])
            resolved = result["resolved_materials"]["result"]
            self.assertEqual(
                resolved["status"],
                "assigned" if operation == "difference" else "conflict",
            )
            if operation == "difference":
                self.assertEqual(resolved["source_features"], ["a"])
            one = evaluate(m, [assign("a")])
            self.assertEqual(
                one["resolved_materials"]["result"]["status"],
                "assigned" if operation == "difference" else "conflict",
            )
            same = evaluate(m, [assign("a"), assign("b", density="2000/2")])
            self.assertEqual(same["resolved_materials"]["result"]["status"], "assigned")
            fixed = evaluate(
                result["model"], [assign("result", "Uniform replacement", "1500")]
            )
            self.assertEqual(
                fixed["resolved_materials"]["result"]["source_features"], ["result"]
            )

    def test_curved_difference_and_conflict_propagate_through_copies(self):
        from test_coaxial_boolean import boolean as curved
        from test_polyhedral_transforms import moved

        for operation in ["union", "difference", "intersection"]:
            m = curved(operation=operation)
            feature = m["features"][-1]
            result = evaluate(
                m, [assign(feature["left"]), assign(feature["right"], "Other", "2000")]
            )
            terminal = result["bodies"][0]["feature_id"]
            self.assertEqual(
                result["resolved_materials"][terminal]["status"],
                "assigned" if operation == "difference" else "conflict",
            )
            shifted = moved(result["model"], (1, 2, 3))
            placed = evaluate(shifted)
            self.assertEqual(
                placed["resolved_materials"][placed["bodies"][0]["feature_id"]],
                result["resolved_materials"][terminal],
            )

    def test_invalid_assignments_and_explicit_removal(self):
        for op, code in [
            (assign("missing"), "missing_feature"),
            (assign("part.profile"), "unsupported_material"),
            (assign("part", ""), "invalid_material"),
            (assign("part", " bad"), "invalid_material"),
            (assign("part", "bad\nname"), "invalid_material"),
            (assign("part", density="0"), "invalid_density"),
            (assign("part", density="-1"), "invalid_density"),
            (assign("part", density="1.5"), "invalid_number"),
        ]:
            with self.assertRaises(CadError) as caught:
                evaluate(model(), [op])
            self.assertEqual(caught.exception.detail["code"], code)
        m = evaluate(model(), [assign("copy")])["model"]
        with self.assertRaises(CadError):
            evaluate(m, [dict(op="remove_feature", id="copy")])
        result = evaluate(
            m,
            [
                dict(op="remove_feature", id="copy"),
                dict(op="clear_material", feature_id="copy"),
            ],
        )
        self.assertNotIn("materials", result["model"])
        bad = copy.deepcopy(m)
        bad["materials"]["missing"] = bad["materials"].pop("copy")
        with self.assertRaises(CadError):
            evaluate(bad)

    def test_persistent_history_mass_and_explicit_density_independence(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "part.cad.json")
            store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(model())
                    + [assign("part"), assign("copy", "Other", "2000")],
                    preserve=[],
                )
            )
            before = store.path.read_bytes()
            command = dict(expected_revision=1, feature_ids=["part", "copy"])
            mass = dispatch_material_mass(store, command)
            self.assertEqual(mass["result"]["mass_kg"], "3/12500")
            self.assertEqual(mass["result"]["center_of_mass_mm"], ["55/3", "2", "1"])
            self.assertEqual(store.path.read_bytes(), before)
            self.assertEqual(dispatch_material_mass(Store(store.path), command), mass)
            preview = store.execute(
                dict(
                    action="preview",
                    expected_revision=1,
                    operations=[assign("part", density="3000")],
                    preserve=[],
                )
            )
            self.assertEqual(
                preview["resolved_materials"]["part"]["material"]["density_kg_per_m3"],
                "3000",
            )
            self.assertEqual(store.path.read_bytes(), before)
            store.execute(
                dict(
                    action="commit",
                    expected_revision=1,
                    transaction_id="density",
                    operations=[assign("part", density="3000")],
                    preserve=[],
                )
            )
            self.assertEqual(
                dispatch_material_mass(store, {**command, "expected_revision": 2})[
                    "result"
                ]["mass_kg"],
                "1/2500",
            )
            store.execute(
                dict(action="undo", expected_revision=2, transaction_id="undo")
            )
            self.assertEqual(
                dispatch_material_mass(store, {**command, "expected_revision": 3})[
                    "result"
                ]["mass_kg"],
                "3/12500",
            )
            from measurements import measure_model

            geometry = measure_model(store.load()["model"], "part")
            self.assertNotIn("mass_properties", geometry)
            self.assertEqual(
                measure_model(store.load()["model"], "part", "500")["mass_properties"][
                    "mass_kg"
                ],
                "1/25000",
            )

    def test_assigned_mass_rejects_missing_conflicting_stale_and_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "part.cad.json")
            m = boolean(
                box("a", [0, 0, 0], [10, 10, 10]),
                box("b", [5, 0, 0], [15, 10, 10]),
                "union",
            )
            store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(m),
                    preserve=[],
                )
            )
            command = dict(expected_revision=1, feature_ids=["result"])
            self.assertEqual(
                dispatch_material_mass(store, command)["error"]["code"],
                "unassigned_material",
            )
            store.execute(
                dict(
                    action="commit",
                    expected_revision=1,
                    transaction_id="material",
                    operations=[assign("a")],
                    preserve=[],
                )
            )
            self.assertEqual(
                dispatch_material_mass(store, {**command, "expected_revision": 2})[
                    "error"
                ]["code"],
                "material_conflict",
            )
            self.assertEqual(
                dispatch_material_mass(store, command)["error"]["code"],
                "revision_conflict",
            )
            self.assertEqual(
                dispatch_material_mass(
                    store, {**command, "feature_ids": ["result", "result"]}
                )["error"]["code"],
                "invalid_command",
            )
