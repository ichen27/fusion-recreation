"""Disposable triangles retain native surface provenance without geometric guessing."""

import json
from fractions import Fraction as F
import math
import unittest
from store import ROOT
from exports import tessellate
from topology import topology_model
from test_counterbores import counterbored
from test_polyhedral_transforms import turned, moved


def number(value):
    return float(F(value))


class SurfaceMesh(unittest.TestCase):
    def audit(self, model, segments=64):
        feature = model["features"][-1]["id"]
        plain = tessellate(model, feature, segments)
        tagged = tessellate(model, feature, segments, include_surfaces=True)
        names = tagged.pop("triangle_surfaces")
        self.assertEqual(plain, tagged)
        surfaces = topology_model(model, feature)["surfaces"]
        self.assertEqual(set(names), set(surfaces))
        self.assertEqual(len(names), len(tagged["triangles"]))
        for indices, name in zip(tagged["triangles"], names):
            points = [tagged["vertices"][i] for i in indices]
            surface = surfaces[name]
            if surface["kind"] == "plane":
                normal = list(map(number, surface["normal"]))
                offset = number(surface["offset"])
                for p in points:
                    self.assertAlmostEqual(
                        sum(a * b for a, b in zip(normal, p)),
                        offset,
                        delta=1e-7 * max(1, math.hypot(*normal)),
                    )
            else:
                axis = surface["axis"]
                origin = list(map(number, surface["origin"]))
                radius = number(surface["radius"])
                for p in points:
                    d = [a - b for a, b in zip(p, origin)]
                    along = sum(a * b for a, b in zip(d, axis))
                    radial = [v - a * along for v, a in zip(d, axis)]
                    self.assertAlmostEqual(math.hypot(*radial), radius, delta=1e-8)

    def test_retained_boundaries_match_native_support_and_untagged_mesh(self):
        for name in [
            "counterbored",
            "turned_counterbored",
            "concave_counterbored",
            "round_counterbored",
            "blind_plate",
            "cavity",
            "separate",
            "through",
        ]:
            model = json.loads(
                (
                    ROOT / f"examples/ai-cad/shared-topology/{name}.model.json"
                ).read_text()
            )
            self.audit(model, 32)
        # All proper quarter-turn frames preserve surface identity and world support.
        for axis in ("x", "y", "z"):
            for turns in (1, 2, 3):
                self.audit(
                    turned(
                        moved(counterbored(), (F(1, 3), F(-2, 5), F(7, 11))),
                        axis,
                        turns,
                    ),
                    16,
                )

    def test_maximum_chord_count_keeps_one_reference_per_triangle(self):
        self.audit(counterbored(), 256)


if __name__ == "__main__":
    unittest.main()
