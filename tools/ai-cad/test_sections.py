"""Independent area/centroid formulas and read-only section protocol checks."""

from fractions import Fraction as F
from pathlib import Path
import random
import tempfile
import unittest
import xml.etree.ElementTree as ET
from sections import (
    section_model,
    section_geometry,
    dispatch_section,
    SectionBudget,
    offset_value,
)
from topology import topology_model
from drawings import NS
from store import Store, CadError
from test_booleans import box, boolean, cases
from test_intersection import operations
from test_plane_cuts import block, cut
from test_polyhedral_transforms import moved
from test_round_stock import cylinder


class Sections(unittest.TestCase):
    def section(self, model, axis="Z", offset="5"):
        return section_model(model, model["features"][-1]["id"], 1, axis, offset)

    def test_cavity_and_through_hole_all_axes(self):
        for axis in "XYZ":
            result = self.section(cases()["cavity"][0], axis)
            self.assertEqual(result["area_mm2"], "64")
            self.assertEqual(result["centroid_mm"], ["5"] * 3)
            self.assertEqual([c["hole"] for c in result["loops"]], [False, True])
        outer = self.section(cases()["cavity"][0], "Z", "1")
        self.assertEqual(outer["area_mm2"], "100")
        self.assertEqual(len(outer["loops"]), 1)
        self.assertEqual(self.section(cases()["through"][0])["area_mm2"], "64")

    def test_disconnected_concave_and_nested_island(self):
        result = self.section(cases()["separate"][0])
        self.assertEqual(result["area_mm2"], "200")
        self.assertEqual(result["centroid_mm"], ["15", "5", "5"])
        self.assertEqual(result["material_regions"], 2)
        result = self.section(cases()["l_shape"][0], offset="1/2")
        self.assertEqual(result["area_mm2"], "3")
        self.assertEqual(result["centroid_mm"], ["5/6", "5/6", "1/2"])
        model = boolean(
            cases()["cavity"][0],
            box("island", [3, 3, 3], [7, 7, 7]),
            "union",
            id="nested",
        )
        result = self.section(model)
        self.assertEqual(result["area_mm2"], "80")
        self.assertEqual(result["centroid_mm"], ["5"] * 3)
        self.assertEqual(result["material_regions"], 2)
        self.assertEqual([c["nesting_depth"] for c in result["loops"]], [0, 1, 2])

    def test_seeded_oblique_tetrahedron_sections_exact_formulas(self):
        rng = random.Random(731)
        for _ in range(30):
            model = block()
            normals = [rng.randint(1, 5) for _ in range(3)]
            limit = rng.randint(5, 50)
            model["parameters"]["diagonal"] = str(limit)
            model["features"].append(cut(normal=list(map(str, normals))))
            depth = rng.randrange(3)
            offset = F(limit, normals[depth] * 3)
            result = self.section(model, "XYZ"[depth], str(offset))
            h, v = [i for i in range(3) if i != depth]
            remainder = limit - normals[depth] * offset
            self.assertEqual(
                F(result["area_mm2"]), remainder**2 / (2 * normals[h] * normals[v])
            )
            centroid = [offset] * 3
            centroid[h], centroid[v] = (
                remainder / (3 * normals[h]),
                remainder / (3 * normals[v]),
            )
            self.assertEqual(list(map(F, result["centroid_mm"])), centroid)

    def test_exact_near_vertex_and_large_translation(self):
        model = block()
        model["features"].append(cut())
        topology = topology_model(model, "diagonal_cut")
        offset = F(60) - F(1, 10**30)
        result = section_geometry(topology, "Z", offset)
        self.assertEqual(F(result["area_mm2"]), F(1, 2 * 10**60))
        original = cases()["cavity"][0]
        translated = moved(original, (10**5, -(10**5), 10**5))
        result = self.section(translated, offset=str(10**5 + 5))
        self.assertEqual(result["area_mm2"], "64")
        self.assertEqual(
            list(map(F, result["centroid_mm"])), [10**5 + 5, -(10**5) + 5, 10**5 + 5]
        )

    def test_svg_holes_and_resource_rejections(self):
        result = self.section(cases()["cavity"][0])
        root = ET.fromstring(result["svg"])
        path = root.find(f"{{{NS}}}path[@id='section-material']")
        self.assertEqual(path.attrib["fill-rule"], "evenodd")
        self.assertEqual(path.attrib["d"].count(" Z"), 2)
        for offset, code in [("2", "section_degenerate"), ("12", "empty_section")]:
            with self.assertRaises(CadError) as caught:
                self.section(cases()["cavity"][0], offset=offset)
            self.assertEqual(caught.exception.detail["code"], code)
        with self.assertRaises(CadError) as caught:
            self.section(cylinder())
        self.assertEqual(caught.exception.detail["code"], "unsupported_section")
        topology = topology_model(cases()["cavity"][0], "result")
        for budget in [SectionBudget(work=0), SectionBudget(seconds=0)]:
            with self.assertRaises(CadError) as caught:
                section_geometry(topology, "Z", F(5), budget)
            self.assertEqual(caught.exception.detail["code"], "section_limit")
        for value in [None, True, 5, "1/0", "1e2", "2.5", "1 mm", "1" * 97]:
            with self.assertRaises(CadError):
                offset_value(value)

    def test_dispatch_revision_cache_and_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "part.cad.json")
            store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(cases()["cavity"][0]),
                    preserve=[],
                )
            )
            before = store.path.read_bytes()
            command = dict(
                expected_revision=1, feature_id="result", axis="Z", offset_mm="5"
            )
            first = dispatch_section(store, command)
            self.assertEqual(first["result"]["area_mm2"], "64")
            self.assertEqual(
                dispatch_section(store, {**command, "offset_mm": "10/2"}), first
            )
            self.assertEqual(
                dispatch_section(store, {**command, "offset_mm": "1"})["result"][
                    "area_mm2"
                ],
                "100",
            )
            for extra, code in [
                ({"expected_revision": 0}, "revision_conflict"),
                ({"axis": "Q"}, "invalid_command"),
                ({"offset_mm": "0"}, "section_degenerate"),
                ({"feature_id": "missing"}, "missing_body"),
            ]:
                reply = dispatch_section(store, {**command, **extra})
                self.assertEqual(reply["error"]["code"], code)
            self.assertEqual(store.path.read_bytes(), before)
