"""Independent orthographic extents, native arc retention and snapshot guards."""

from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from drawings import NS, drawing_model, dispatch_drawing
from store import CadError, Store, encode
from test_intersection import rectangle, operations
from test_round_stock import cylinder
from test_holes import perforated
from test_revolution import revolved
from test_booleans import cases
from test_polyhedral_transforms import moved, turned


def parse(result):
    return ET.fromstring(result["svg"])


def paths(result, view):
    return parse(result).find(f"{{{NS}}}g[@id='view-{view}']").findall(f"{{{NS}}}path")


class Drawings(unittest.TestCase):
    def test_box_projection_orientation_independent_page_coordinates_and_metadata(self):
        model = rectangle("box", 0, 0, 10, 4, 2)
        result = drawing_model(model, "box", 7)
        self.assertEqual(result["extents_mm"], ["10", "4", "2"])
        self.assertEqual(
            result["source_model_sha256"], hashlib.sha256(encode(model)).hexdigest()
        )
        for view, bounds in [
            ("top", (70, 163, 430, 307)),
            ("front", (70, 484, 430, 556)),
            ("right", (678, 484, 822, 556)),
        ]:
            points = []
            for path in paths(result, view):
                tokens = path.attrib["d"].split()
                self.assertEqual(tokens[0], "M")
                self.assertEqual(tokens[3], "L")
                points += [
                    tuple(map(float, tokens[1:3])),
                    tuple(map(float, tokens[4:6])),
                ]
            self.assertEqual(
                (
                    min(x for x, y in points),
                    min(y for x, y in points),
                    max(x for x, y in points),
                    max(y for x, y in points),
                ),
                bounds,
            )
        self.assertEqual(
            [
                (v["line_edges"], v["arc_edges"], v["collapsed_edges"])
                for v in result["views"]
            ],
            [(8, 0, 4)] * 3,
        )
        root = parse(result)
        self.assertEqual(
            json.loads(root.find(f"{{{NS}}}metadata").text),
            {k: v for k, v in result.items() if k != "svg"},
        )
        self.assertIn("No hidden-line removal", root.find(f"{{{NS}}}desc").text)
        self.assertIsNone(root.find(f"{{{NS}}}script"))

    def test_circles_remain_quarter_arcs_and_edge_on_projections_are_lines(self):
        for model, face_view in [
            (cylinder(radius="5", height="12"), "top"),
            (turned(cylinder(radius="5", height="12"), "x", 1), "front"),
            (turned(cylinder(radius="5", height="12"), "y", 1), "right"),
        ]:
            result = drawing_model(model, model["features"][-1]["id"], 1)
            for view in result["views"]:
                self.assertEqual(
                    view["arc_edges"], 8 if view["name"] == face_view else 0
                )
                for path in paths(result, view["name"]):
                    tokens = path.attrib["d"].split()
                    if tokens[3] == "A":
                        self.assertEqual(tokens[4], tokens[5])
                        self.assertEqual(tokens[6:8], ["0", "0"])
                        self.assertIn(tokens[8], ["0", "1"])
                        a = list(map(float, tokens[1:3]))
                        b = list(map(float, tokens[9:11]))
                        radius = float(tokens[4])
                        sign = 1 if tokens[8] == "1" else -1
                        implied_center = [
                            (a[0] + b[0]) / 2 - sign * (b[1] - a[1]) / 2,
                            (a[1] + b[1]) / 2 + sign * (b[0] - a[0]) / 2,
                        ]
                        expected_center = {
                            "top": [250, 235],
                            "front": [250, 520],
                            "right": [750, 520],
                        }[face_view]
                        for got, wanted in zip(implied_center, expected_center):
                            self.assertAlmostEqual(got, wanted, delta=1e-7)
                        # A true quarter circle has a chord of sqrt(2)*radius.
                        self.assertAlmostEqual(
                            sum((a[i] - b[i]) ** 2 for i in range(2)),
                            2 * radius**2,
                            delta=1e-5,
                        )

    def test_native_shapes_and_large_translation_preserve_projected_linework(self):
        for model in [
            perforated(),
            revolved(),
            cases()["cavity"][0],
            cases()["separate"][0],
        ]:
            feature = model["features"][-1]["id"]
            result = drawing_model(model, feature, 1)
            moved_model = moved(model, (100000, -200000, 300000))
            translated = drawing_model(
                moved_model, moved_model["features"][-1]["id"], 2
            )
            self.assertEqual(result["extents_mm"], translated["extents_mm"])
            for view in ["top", "front", "right"]:
                self.assertEqual(
                    [p.attrib["d"] for p in paths(result, view)],
                    [p.attrib["d"] for p in paths(translated, view)],
                )
            self.assertNotEqual(
                result["source_model_sha256"], translated["source_model_sha256"]
            )

    def test_tiny_geometry_normalizes_and_unrepresentable_detail_rejects(self):
        small = rectangle("box", 0, 0, F(1, 10**20), F(1, 10**20), F(1, 10**20))
        result = drawing_model(small, "box", 1)
        self.assertNotRegex(result["svg"], re.compile(r"(?:NaN|Infinity)"))
        thin = rectangle("box", 0, 0, 10, F(1, 10**20), 2)
        with self.assertRaises(CadError) as caught:
            drawing_model(thin, "box", 1)
        self.assertEqual(caught.exception.detail["code"], "drawing_precision")

    def test_hidden_svg_style_preserves_intervals_order_and_cache_separation(self):
        simple = drawing_model(
            rectangle("box", 0, 0, 10, 4, 2), "box", 1, "planar_hidden"
        )
        self.assertEqual(
            [(v["visible_segments"], v["hidden_segments"]) for v in simple["views"]],
            [(4, 0)] * 3,
        )
        model = cases()["cavity"][0]
        result = drawing_model(model, "result", 1, "planar_hidden")
        self.assertEqual(result["representation"], "orthographic_planar_hidden")
        for view in ("top", "front", "right"):
            drawn = paths(result, view)
            hidden = [p for p in drawn if p.attrib["data-visibility"] == "hidden"]
            visible = [p for p in drawn if p.attrib["data-visibility"] == "visible"]
            self.assertTrue(hidden and visible)
            self.assertEqual(drawn, hidden + visible)
            self.assertTrue(
                all(p.attrib.get("stroke-dasharray") == "5 4" for p in hidden)
            )
            self.assertTrue(all("stroke-dasharray" not in p.attrib for p in visible))
            self.assertTrue(
                all(
                    F(p.attrib["data-t-start"]) < F(p.attrib["data-t-end"])
                    for p in drawn
                )
            )
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
            command = dict(expected_revision=1, feature_id="result")
            before = store.path.read_bytes()
            hidden = dispatch_drawing(store, {**command, "style": "planar_hidden"})
            wire = dispatch_drawing(store, command)
            self.assertNotEqual(hidden["result"]["svg"], wire["result"]["svg"])
            self.assertEqual(
                dispatch_drawing(store, {**command, "style": "all_edges"}), wire
            )
            self.assertEqual(
                dispatch_drawing(store, {**command, "style": "planar_hidden"}), hidden
            )
            self.assertEqual(
                dispatch_drawing(store, {**command, "style": "unknown"})["error"][
                    "code"
                ],
                "invalid_command",
            )
            self.assertEqual(store.path.read_bytes(), before)

    def test_revision_cache_and_read_only_native_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.cad.json"
            store = Store(path)
            store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(rectangle("box", 0, 0, 10, 4, 2)),
                    preserve=[],
                )
            )
            before = path.read_bytes()
            command = dict(expected_revision=1, feature_id="box")
            first = dispatch_drawing(store, command)
            self.assertEqual(dispatch_drawing(store, command), first)
            self.assertEqual(
                dispatch_drawing(store, {**command, "expected_revision": 0})["error"][
                    "code"
                ],
                "revision_conflict",
            )
            self.assertEqual(
                dispatch_drawing(store, {**command, "feature_id": "missing"})["error"][
                    "code"
                ],
                "missing_body",
            )
            self.assertEqual(path.read_bytes(), before)
            store.execute(
                dict(
                    action="commit",
                    expected_revision=1,
                    transaction_id="taller",
                    operations=[dict(op="set_parameter", id="box.height", mm="3")],
                    preserve=[],
                )
            )
            second = dispatch_drawing(store, {**command, "expected_revision": 2})
            self.assertEqual(second["result"]["extents_mm"], ["10", "4", "3"])
            self.assertNotEqual(
                second["result"]["source_model_sha256"],
                first["result"]["source_model_sha256"],
            )
