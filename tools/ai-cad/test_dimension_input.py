"""Dimension entry is exact at the command boundary, never a float/model parser."""

import copy
import json
from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest

from store import CadError, Store, dispatch, evaluate


def create():
    return {
        "action": "commit",
        "expected_revision": 0,
        "transaction_id": "unit-stock",
        "preserve": [],
        "operations": [
            {"op": "define_parameter", "id": "width", "mm": "1/2 in"},
            {"op": "define_parameter", "id": "depth", "mm": "2.54 cm"},
            {"op": "define_parameter", "id": "height", "mm": ".01 m"},
            {
                "op": "add_feature",
                "feature": {
                    "kind": "block",
                    "id": "stock",
                    "width": "width",
                    "depth": "depth",
                    "height": "height",
                },
            },
        ],
    }


class DimensionEntry(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "units.cad.json"
        self.store = Store(self.path)

    def edit(self, value, *, operation="set_parameter", preserve=None, revision=1):
        return {
            "action": "commit",
            "expected_revision": revision,
            "transaction_id": "edit-" + str(revision),
            "preserve": preserve or [],
            "operations": [
                {
                    "op": operation,
                    "id": "width",
                    "delta_mm" if operation == "adjust_parameter" else "mm": value,
                }
            ],
        }

    def test_preview_commit_reopen_and_undo_canonical_geometry(self):
        preview = create() | {"action": "preview"}
        preview.pop("transaction_id")
        result = self.store.execute(preview)
        self.assertFalse(self.path.exists())
        saved = self.store.execute(create())
        self.assertEqual(result["model"], saved["model"])
        self.assertEqual(
            saved["model"]["parameters"],
            {"width": "127/10", "depth": "127/5", "height": "10"},
        )
        self.assertEqual(
            F(saved["bodies"][0]["volume_mm3"]), F(127, 10) * F(127, 5) * 10
        )
        canonical = copy.deepcopy(saved["model"])
        self.assertEqual(saved["bodies"], evaluate(canonical)["bodies"])
        before = self.path.read_bytes()
        command = self.edit("-1/4 in", operation="adjust_parameter")
        preview = command | {"action": "preview"}
        preview.pop("transaction_id")
        self.store.execute(preview)
        self.assertEqual(self.path.read_bytes(), before)
        changed = self.store.execute(command)
        self.assertEqual(changed["model"]["parameters"]["width"], "127/20")
        reopened = Store(self.path)
        self.assertEqual(
            reopened.execute({"action": "inspect"})["model"], changed["model"]
        )
        self.assertEqual(
            json.loads(self.path.read_text())["state"]["model"], changed["model"]
        )
        undo = reopened.execute(
            {"action": "undo", "expected_revision": 2, "transaction_id": "undo"}
        )
        self.assertEqual(undo["model"], canonical)

    def test_fixed_and_preserved_values_compare_physical_values(self):
        command = create()
        command["operations"].append({"op": "fix_parameter", "id": "width"})
        self.store.execute(command)
        same_command = self.edit("12.700 mm", preserve=["width"])
        same_command["operations"].append(
            {"op": "set_parameter", "id": "depth", "mm": "3 cm"}
        )
        same = self.store.execute(same_command)
        self.assertEqual(same["model"]["parameters"]["width"], "127/10")
        before = self.path.read_bytes()
        rejected = dispatch(self.store, self.edit(".6 in", revision=2))
        self.assertEqual(rejected["error"]["code"], "constraint_conflict")
        self.assertEqual(self.path.read_bytes(), before)

    def test_preserve_conflict_and_invalid_literals_are_atomic(self):
        self.store.execute(create())
        before = self.path.read_bytes()
        self.assertEqual(
            dispatch(self.store, self.edit("1 in", preserve=["width"]))["error"][
                "code"
            ],
            "preserve_conflict",
        )
        for text in [
            "1e3",
            "1.2.3",
            "1 1/2 in",
            "1 yd",
            "1/0 cm",
            "NaN",
            "1 + 2",
            "0." + "0" * 39 + "1",
            str(2**127 - 1) + " m",
        ]:
            command = self.edit(text)
            command["operations"].insert(
                0, {"op": "set_parameter", "id": "depth", "mm": "3 cm"}
            )
            self.assertEqual(
                dispatch(self.store, command)["error"]["code"], "invalid_number", text
            )
            self.assertEqual(self.path.read_bytes(), before)

    def test_tiny_decimal_has_no_float_round_trip_and_native_schema_stays_strict(self):
        command = create()
        command["operations"][0]["mm"] = "0.000000000000000000000000000001"
        result = self.store.execute(command)
        self.assertEqual(F(result["model"]["parameters"]["width"]), F(1, 10**30))
        self.assertEqual(F(result["bodies"][0]["volume_mm3"]), F(254, 10**30))
        for text in ["1.5", "1 in"]:
            model = copy.deepcopy(result["model"])
            model["parameters"]["width"] = text
            with self.assertRaises(CadError) as caught:
                evaluate(model)
            self.assertEqual(caught.exception.detail["code"], "invalid_number")


if __name__ == "__main__":
    unittest.main()
