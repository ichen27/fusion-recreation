"""Exact convex planar lofts with matched vertex identities and explicit rejection."""

from pathlib import Path
import tempfile
import unittest
from fractions import Fraction as F
from store import CadError, Store, evaluate
from exports import tessellate
from topology import topology_model
from measurements import measure_model
from test_holes import audit_triangles
from test_intersection import operations
from test_polyhedral_transforms import moved, turned


def loft(bottom=None, top=None, height="12", reverse=False):
    bottom = bottom or [(0, 0), (40, 0), (40, 20), (0, 20)]
    top = top or [(5, 5), (35, 5), (35, 15), (5, 15)]
    m = dict(parameters={"height": height}, fixed={}, features=[])
    for name, points in [("bottom", bottom), ("top", top)]:
        vertices = []
        for i, (x, y) in enumerate(points):
            m["parameters"].update({f"{name}.{i}.x": str(x), f"{name}.{i}.y": str(y)})
            vertices.append(dict(id=f"v{i}", x=f"{name}.{i}.x", y=f"{name}.{i}.y"))
        m["features"].append(
            dict(
                kind="planar_profile",
                id=name,
                vertices=vertices[::-1] if reverse else vertices,
            )
        )
    m["features"].append(
        dict(kind="planar_loft", id="part", bottom="bottom", top="top", height="height")
    )
    return m


class PlanarLoft(unittest.TestCase):
    def test_closed_form_volume_centroid_and_planar_surfaces(self):
        # A(z) = (40-10*z/h)*(20-10*z/h); integrate independently.
        for reverse in (False, True):
            m = loft(reverse=reverse)
            body = evaluate(m)["bodies"][0]
            self.assertEqual(body["volume_mm3"], "6400")
            self.assertNotIn("analytic", body)
            values = measure_model(m, "part")
            self.assertEqual(values["centroid_mm"], ["20", "10", "81/16"])
            self.assertEqual(len(topology_model(m, "part")["faces"]), 6)
            mesh = tessellate(m, "part", 32, True)
            triangles = [
                [tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]
            ]
            self.assertAlmostEqual(audit_triangles(triangles, 0), 6400)
        # Independent winding and cyclic start points do not change correspondence.
        m = loft()
        m["features"][1]["vertices"].reverse()
        self.assertEqual(evaluate(m)["bodies"][0]["volume_mm3"], "6400")
        m["features"][1]["vertices"] = (
            m["features"][1]["vertices"][1:] + m["features"][1]["vertices"][:1]
        )
        self.assertEqual(evaluate(m)["bodies"][0]["volume_mm3"], "6400")

    def test_skew_equal_sections_placement_and_later_planar_cut(self):
        base = [(0, 0), (40, 0), (40, 20), (0, 20)]
        m = loft(base, [(x + 7, y - 3) for x, y in base], "9/2")
        self.assertEqual(evaluate(m)["bodies"][0]["volume_mm3"], "3600")
        self.assertEqual(
            measure_model(m, "part")["centroid_mm"], ["47/2", "17/2", "9/4"]
        )
        for axis in "xyz":
            transformed = turned(moved(m, (1, 2, 3)), axis, 1)
            self.assertEqual(evaluate(transformed)["bodies"][0]["volume_mm3"], "3600")
            topology_model(transformed, "turned")
        m = loft()
        m["parameters"]["half"] = "6"
        m["features"].append(
            dict(
                kind="plane_cut",
                id="cut",
                input="part",
                normal=["0", "0", "1"],
                offset="half",
            )
        )
        self.assertEqual(evaluate(m)["bodies"][0]["volume_mm3"], "3950")

    def test_nonplanar_twisted_concave_missing_ids_and_bad_height_reject(self):
        cases = []
        m = loft()
        m["parameters"]["top.1.y"] = str(F(5) + F(1, 10**30))
        cases.append((m, "unsupported_loft"))
        m = loft()
        m["parameters"]["top.1.y"] = "6"
        cases.append((m, "unsupported_loft"))
        m = loft()
        m["features"][1]["vertices"][0]["id"] = "other"
        cases.append((m, "unsupported_loft"))
        m = loft()
        m["features"][1]["vertices"][0]["id"], m["features"][1]["vertices"][1]["id"] = (
            "v1",
            "v0",
        )
        cases.append((m, "unsupported_loft"))
        m = loft(top=[(5, 5), (35, 5), (10, 8), (5, 15)])
        cases.append((m, "unsupported_loft"))
        m = loft(height="0")
        cases.append((m, "dimension_range"))
        m = loft()
        m["features"][-1]["top"] = "part"
        cases.append((m, "unsupported_reference"))
        for model, code in cases:
            with self.subTest(code=code), self.assertRaises(CadError) as caught:
                evaluate(model)
            self.assertEqual(caught.exception.detail["code"], code)

    def test_upstream_links_preview_rejection_reopen_undo(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.json"
            store = Store(path)
            created = store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(loft()),
                    preserve=[],
                )
            )
            before = path.read_bytes()
            edit = dict(
                expected_revision=1,
                operations=[dict(op="set_parameter", id="height", mm="24")],
                preserve=[],
            )
            self.assertEqual(
                store.execute(dict(action="preview", **edit))["bodies"][0][
                    "volume_mm3"
                ],
                "12800",
            )
            self.assertEqual(path.read_bytes(), before)
            store.execute(dict(action="commit", transaction_id="tall", **edit))
            saved = path.read_bytes()
            with self.assertRaises(CadError):
                store.execute(
                    dict(
                        action="commit",
                        expected_revision=2,
                        transaction_id="twist",
                        operations=[dict(op="set_parameter", id="top.1.y", mm="6")],
                        preserve=[],
                    )
                )
            self.assertEqual(path.read_bytes(), saved)
            self.assertEqual(
                Store(path).execute(
                    dict(action="undo", expected_revision=2, transaction_id="undo")
                )["bodies"],
                created["bodies"],
            )
            m = loft()
            m["relations"] = {"top.0.x": dict(offset_mm="0", terms={"top.3.x": "1"})}
            changed = evaluate(m, [dict(op="set_parameter", id="top.3.x", mm="8")])
            self.assertEqual(changed["model"]["parameters"]["top.0.x"], "8")
            self.assertNotEqual(changed["bodies"], created["bodies"])
