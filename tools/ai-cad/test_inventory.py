"""Identity/counting, exact values, CSV safety and revision-bound reads."""

import csv
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from inventory import dispatch_inventory, csv_cell
from store import Store, encode
from test_booleans import box, boolean
from test_interference import pair
from test_intersection import operations
from test_instances import instance
from test_linear_pattern import pattern
from test_materials import assign, model
from test_round_stock import cylinder


class Inventory(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = Store(Path(self.directory.name) / "part.cad.json")

    def create(self, source, extra=()):
        self.store.execute(
            dict(
                action="commit",
                expected_revision=0,
                transaction_id="create",
                operations=operations(source) + list(extra),
                preserve=[],
            )
        )
        return self.read(1)

    def read(self, revision):
        before = self.store.path.read_bytes() if self.store.path.exists() else None
        reply = dispatch_inventory(self.store, dict(expected_revision=revision))
        after = self.store.path.read_bytes() if self.store.path.exists() else None
        self.assertEqual(before, after)
        self.assertIn("result", reply, reply)
        return reply["result"]

    def test_equal_volume_different_shapes_and_overlapping_copies_stay_distinct(self):
        source = pair(
            instance(box("a", [0, 0, 0], [10, 4, 2]), offset=(0, 0, 0)),
            box("b", [0, 0, 0], [5, 8, 2]),
        )
        result = self.create(source)
        self.assertEqual(result["solid_count"], 3)
        self.assertEqual([r["feature_id"] for r in result["rows"]], ["a", "b", "copy"])
        self.assertEqual([r["volume_mm3"] for r in result["rows"]], ["80"] * 3)
        self.assertEqual([r["quantity"] for r in result["rows"]], [1] * 3)
        self.assertEqual(
            [r["linked_source"] for r in result["rows"]], [None, None, "a"]
        )
        self.assertEqual(
            result["material_counts"], dict(assigned=0, unassigned=3, conflict=0)
        )

    def test_disconnected_pattern_is_one_terminal_body(self):
        result = self.create(pattern())
        self.assertEqual(result["solid_count"], 1)
        self.assertEqual(result["rows"][0]["feature_id"], "pattern")
        self.assertEqual(result["rows"][0]["quantity"], 1)
        self.assertEqual(result["rows"][0]["volume_mm3"], "72000")

    def test_empty_and_standalone_profiles_do_not_invent_parts(self):
        self.assertEqual(self.read(0)["rows"], [])
        source = box("outline", [0, 0, 0], [10, 4, 2])
        source["features"].pop()
        self.assertEqual(self.create(source)["rows"], [])

    def test_symbolic_curved_volume_stays_exact(self):
        result = self.create(cylinder(radius="3", height="2"))
        self.assertEqual(result["rows"][0]["volume_mm3"], "18*pi")
        row = next(csv.DictReader(io.StringIO(result["csv"])))
        self.assertEqual(row["volume_mm3"], "18*pi")

    def test_material_inheritance_unicode_csv_and_read_reopen_undo(self):
        name = '=Copper, "测试"'
        source = self.create(model(), [assign("part", name, "2000/2")])
        self.assertEqual(source["material_counts"]["assigned"], 2)
        csv_rows = list(csv.DictReader(io.StringIO(source["csv"])))
        self.assertEqual(csv_rows[0]["material_name"], "'" + name)
        self.assertEqual(source["rows"][0]["material"]["material"]["name"], name)
        self.assertEqual(
            source["source_model_sha256"],
            hashlib.sha256(encode(self.store.load()["model"])).hexdigest(),
        )
        self.store.execute(
            dict(
                action="commit",
                expected_revision=1,
                transaction_id="resize",
                operations=[dict(op="set_parameter", id="part.height", mm="3")],
                preserve=[],
            )
        )
        self.store = Store(self.store.path)
        changed = self.read(2)
        self.assertEqual([r["volume_mm3"] for r in changed["rows"]], ["120"] * 2)
        self.assertNotEqual(
            changed["source_model_sha256"], source["source_model_sha256"]
        )
        self.store.execute(
            dict(action="undo", expected_revision=2, transaction_id="undo")
        )
        restored = self.read(3)
        self.assertEqual(restored["rows"], source["rows"])
        self.assertEqual(restored["source_model_sha256"], source["source_model_sha256"])

    def test_material_conflict_and_override_are_reported(self):
        source = boolean(
            box("a", [0, 0, 0], [10, 10, 10]),
            box("b", [5, 0, 0], [15, 10, 10]),
            "union",
        )
        result = self.create(source, [assign("a"), assign("b", "Other", "2000")])
        self.assertEqual(result["material_counts"]["conflict"], 1)
        row = next(csv.DictReader(io.StringIO(result["csv"])))
        self.assertEqual(row["density_kg_per_m3"], "")
        self.store.execute(
            dict(
                action="commit",
                expected_revision=1,
                transaction_id="override",
                operations=[assign("result")],
                preserve=[],
            )
        )
        self.assertEqual(self.read(2)["material_counts"]["assigned"], 1)

    def test_stale_bool_revision_unknown_fields_and_csv_literals(self):
        self.create(model())
        for command, code in [
            (dict(expected_revision=0), "revision_conflict"),
            (dict(expected_revision=True), "revision_conflict"),
            (dict(expected_revision=1, feature_id="part"), "invalid_command"),
            ([], "invalid_command"),
        ]:
            self.assertEqual(
                dispatch_inventory(self.store, command)["error"]["code"], code
            )
        for value in ["=1+1", "+2", "-3", "@SUM(A1)", "  =1"]:
            self.assertEqual(csv_cell(value), "'" + value)
        for value in ["Steel", "18*pi", "1/3", ""]:
            self.assertEqual(csv_cell(value), value)
