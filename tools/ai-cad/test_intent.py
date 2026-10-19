"""Explicit provenance, shared-dimension impact and constrained drivers."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from intent import explain_model, dispatch_explain
from store import ROOT, Store, CadError, evaluate
from test_contract import CREATE


class Intent(unittest.TestCase):
    def test_shared_driver_impacts_parts_outside_selected_source_chain(self):
        model = {
            "parameters": {"width": "20", "half": "10", "height": "5", "depth": "8"},
            "fixed": {"height": "5"},
            "relations": {"half": {"offset_mm": "0", "terms": {"width": "1/2"}}},
            "features": [
                {
                    "kind": "block",
                    "id": "first",
                    "width": "width",
                    "depth": "depth",
                    "height": "height",
                },
                {
                    "kind": "block",
                    "id": "second",
                    "width": "half",
                    "depth": "depth",
                    "height": "height",
                },
            ],
        }
        before = copy.deepcopy(model)
        info = explain_model(model, "second")
        self.assertEqual(model, before)
        self.assertTrue(info["terminal_body"])
        self.assertEqual([f["id"] for f in info["source_features"]], ["second"])
        half = info["parameters"]["half"]
        self.assertFalse(half["directly_editable"])
        self.assertEqual(half["driving_parameters"], ["width"])
        self.assertEqual(
            info["parameters"]["width"]["affected_bodies"], ["first", "second"]
        )
        self.assertEqual(info["parameters"]["width"]["affected_parameters"], ["half"])
        self.assertFalse(info["parameters"]["height"]["directly_editable"])
        self.assertEqual(info["parameters"]["height"]["fixed_mm"], "5")
        info = explain_model(model, "first")
        self.assertNotIn("half", info["parameters"])
        self.assertEqual(
            info["parameters"]["width"]["affected_bodies"], ["first", "second"]
        )
        # An actual edit reaches both bodies, including the one outside the source chain.
        changed = evaluate(model, [{"op": "set_parameter", "id": "width", "mm": "40"}])
        self.assertEqual([b["volume_mm3"] for b in changed["bodies"]], ["1600", "800"])

    def test_retained_feature_dependencies_and_literal_normal_not_parameter(self):
        model = json.loads(
            (ROOT / "examples/ai-cad/quarter-turn/edited.cad.json").read_text()
        )["state"]["model"]
        info = explain_model(model, "stock2")
        self.assertFalse(info["terminal_body"])
        self.assertEqual(info["downstream_features"], ["turn1", "intersection1"])
        info = explain_model(model, "intersection1")
        self.assertEqual(
            [f["id"] for f in info["source_features"]],
            ["stock1", "stock2", "turn1", "intersection1"],
        )
        self.assertEqual(
            info["parameters"]["turn1.x"]["affected_features"],
            ["turn1", "intersection1"],
        )
        self.assertNotIn("z", info["parameters"])
        from test_plane_cuts import tetra

        plane_model = tetra()
        info = explain_model(plane_model, plane_model["features"][-1]["id"])
        self.assertNotIn("1", info["parameters"])

    def test_transitive_drivers_and_consumers_for_shared_profile(self):
        model = {
            "parameters": {"a": "20", "b": "10", "c": "5", "zero": "0", "h": "2"},
            "fixed": {"a": "20"},
            "relations": {
                "b": {"offset_mm": "0", "terms": {"a": "1/2"}},
                "c": {"offset_mm": "0", "terms": {"b": "1/2"}},
            },
            "features": [
                {
                    "kind": "planar_profile",
                    "id": "profile",
                    "vertices": [
                        {"id": "a", "x": "zero", "y": "zero"},
                        {"id": "b", "x": "c", "y": "zero"},
                        {"id": "c", "x": "zero", "y": "c"},
                    ],
                },
                {"kind": "extrude", "id": "one", "profile": "profile", "height": "h"},
                {"kind": "extrude", "id": "two", "profile": "profile", "height": "h"},
            ],
        }
        info = explain_model(model, "one")
        self.assertEqual(info["parameters"]["c"]["driving_parameters"], ["a"])
        self.assertFalse(info["parameters"]["a"]["directly_editable"])
        self.assertEqual(info["parameters"]["a"]["affected_parameters"], ["b", "c"])
        self.assertEqual(info["parameters"]["a"]["affected_bodies"], ["one", "two"])
        self.assertEqual(
            info["parameters"]["zero"]["affected_features"], ["profile", "one", "two"]
        )

    def test_revision_errors_and_explanation_never_write_native_state(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "model.json")
            state = store.execute(CREATE)
            feature = state["bodies"][0]["feature_id"]
            before = store.path.read_bytes()
            command = {"expected_revision": 1, "feature_id": feature}
            first = dispatch_explain(store, command)
            self.assertIn("result", first)
            self.assertEqual(dispatch_explain(store, command), first)
            for command, code in [
                ({"expected_revision": 0, "feature_id": feature}, "revision_conflict"),
                (
                    {"expected_revision": True, "feature_id": feature},
                    "revision_conflict",
                ),
                ({"expected_revision": 1, "feature_id": "absent"}, "missing_feature"),
                ([], "invalid_command"),
            ]:
                self.assertEqual(
                    dispatch_explain(store, command)["error"]["code"], code
                )
            self.assertEqual(store.path.read_bytes(), before)

    def test_hole_and_transform_references_have_explicit_semantics(self):
        from test_holes import perforated
        from test_blind_holes import blind
        from test_round_stock import flange
        from test_translation import moved
        from test_plane_cuts import tetra

        for model in [perforated(), blind(perforated()), flange(), blind(flange())]:
            feature = model["features"][-1]
            info = explain_model(model, feature["id"])
            links = info["source_features"][-1]
            expected = {h[k] for h in feature["holes"] for k in ["x", "y", "radius"]}
            if feature["kind"] == "blind_holes":
                expected.add(feature["depth"])
            self.assertEqual(set(links["parameters"]), expected)
            self.assertEqual(links["inputs"], [feature["input"]])
            for parameter in expected:
                self.assertEqual(
                    info["parameters"][parameter]["affected_bodies"], [feature["id"]]
                )
        model = moved(tetra(), ["1/3", "-2", "5"])
        info = explain_model(model, "moved")
        self.assertEqual(
            info["source_features"][-1]["parameters"], model["features"][-1]["offset"]
        )

    def test_invalid_model_never_receives_a_planning_explanation(self):
        with self.assertRaises(CadError):
            explain_model(
                {
                    "parameters": {},
                    "fixed": {},
                    "features": [
                        {
                            "kind": "block",
                            "id": "b",
                            "width": "missing",
                            "depth": "missing",
                            "height": "missing",
                        }
                    ],
                },
                "b",
            )
