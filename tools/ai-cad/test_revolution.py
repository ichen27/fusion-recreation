"""Exact turned profiles: independent closed forms, boundaries and reversible edits."""

from fractions import Fraction as F
import math
from pathlib import Path
import tempfile
import unittest
from exports import tessellate
from measurements import measure_model
from topology import topology_model
from store import CadError, Store, dispatch, evaluate
from test_profiles import model_for
from test_intersection import operations
from test_holes import audit_triangles
from test_analytic_measurements import exact_value
from test_polyhedral_transforms import moved, turned


def revolved(points=None, reverse=False):
    points = points or [(0, 0), (10, 0), (10, 5), (6, 5), (6, 12), (0, 12)]
    m = model_for(points, "1", reverse)
    m["features"][0]["kind"] = "planar_profile"
    m["features"][-1] = dict(
        kind="revolve", id="revolved", profile=m["features"][0]["id"]
    )
    return m


class Revolution(unittest.TestCase):
    def test_ring_closed_forms_and_axis_filled_stepped_shaft(self):
        for points, coefficient, z, genus in [
            ([(3, 0), (10, 0), (10, 12), (3, 12)], F(1092), F(6), 1),
            (None, F(752), F(212, 47), 0),
            ([(3, 0), (10, 0), (5, 12), (2, 12)], F(624), F(0), 1),
        ]:
            model = revolved(points)
            body = evaluate(model)["bodies"][0]
            self.assertEqual(
                F(body["analytic"]["volume"]["pi_subtract_mm3"]), -coefficient
            )
            topology = topology_model(model, "revolved")
            self.assertEqual(topology["shell_euler"], [2 - 2 * genus])
            values = measure_model(model, "revolved")
            if z:
                self.assertEqual(F(values["centroid_mm"][2]), z)
            for segments in [16, 64, 256]:
                mesh = tessellate(model, "revolved", segments, True)
                triangles = [
                    [tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]
                ]
                volume = audit_triangles(triangles, genus)
                self.assertAlmostEqual(
                    volume,
                    float(coefficient) * segments * math.sin(math.tau / segments) / 2,
                    places=7,
                )
                self.assertEqual(
                    set(mesh["triangle_surfaces"]), set(topology["surfaces"])
                )
        ring = measure_model(revolved([(3, 0), (10, 0), (10, 12), (3, 12)]), "revolved")
        tensor = [
            [exact_value(v, F(3)) for v in row]
            for row in ring["centroidal_volume_inertia_mm5"]
        ]
        self.assertEqual(
            tensor, [[42861 * 3, 0, 0], [0, 42861 * 3, 0], [0, 0, 59514 * 3]]
        )

    def test_reversed_profile_negative_z_and_exact_placements(self):
        points = [(0, -4), (10, -4), (10, 8), (0, 8)]
        a, b = revolved(points), revolved(points, True)
        self.assertEqual(measure_model(a, "revolved"), measure_model(b, "revolved"))
        base = measure_model(a, "revolved")
        self.assertEqual(base["centroid_mm"], ["0", "0", "2"])
        shifted = moved(a, [F(1, 3), F(-2, 7), F(5, 11)])
        mid = shifted["features"][-1]["id"]
        measured = measure_model(shifted, mid)
        self.assertEqual(measured["centroid_mm"], ["1/3", "-2/7", "27/11"])
        self.assertEqual(
            base["centroidal_volume_inertia_mm5"],
            measured["centroidal_volume_inertia_mm5"],
        )
        rotated = turned(a, "x", 1)
        rid = rotated["features"][-1]["id"]
        self.assertEqual(measure_model(rotated, rid)["centroid_mm"], ["0", "-2", "0"])
        self.assertEqual(topology_model(rotated, rid)["shell_euler"], [2])
        mesh = tessellate(rotated, rid, 32, True)
        audit_triangles(
            [[tuple(mesh["vertices"][i]) for i in t] for t in mesh["triangles"]], 0
        )

    def test_axis_crossing_apex_and_disconnected_axis_contacts_reject(self):
        for points in [
            [(-1, 0), (10, 0), (10, 12), (-1, 12)],
            [(0, 0), (10, 0), (0, 12)],
            [(0, 0), (10, 1), (10, 12), (0, 12)],
            [(0, 0), (10, 0), (10, 12), (0, 12), (1, 6)],
        ]:
            with self.assertRaises(CadError) as caught:
                evaluate(revolved(points))
            self.assertEqual(caught.exception.detail["code"], "unsupported_revolution")

    def test_exact_scale_limits_source_links_and_unsupported_planar_operations(self):
        from intent import explain_model
        from test_instances import instance

        for scale in [F(1, 10**30), F(1, 3), F(100000)]:
            model = revolved([(0, 0), (scale, 0), (scale, 2 * scale), (0, 2 * scale)])
            result = evaluate(model)["bodies"][0]
            self.assertEqual(
                F(result["analytic"]["volume"]["pi_subtract_mm3"]), -2 * scale**3
            )
            self.assertEqual(
                measure_model(model, "revolved")["centroid_mm"], ["0", "0", str(scale)]
            )
            self.assertEqual(topology_model(model, "revolved")["shell_euler"], [2])
        model = instance(revolved())
        radius = model["features"][0]["vertices"][1]["x"]
        info = explain_model(model, "copy")
        self.assertEqual(
            set(info["parameters"][radius]["affected_bodies"]), {"revolved", "copy"}
        )
        model["parameters"][radius] = "12"
        self.assertEqual(
            {b["volume_mm3"] for b in evaluate(model)["bodies"]}, {"972*pi"}
        )
        model = revolved()
        model["parameters"]["cut_z"] = "6"
        model["features"].append(
            dict(
                kind="plane_cut",
                id="cut",
                input="revolved",
                normal=["0", "0", "1"],
                offset="cut_z",
            )
        )
        with self.assertRaises(CadError) as caught:
            evaluate(model)
        self.assertEqual(caught.exception.detail["code"], "unsupported_reference")

    def test_profile_edit_preview_reopen_and_undo(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.json"
            store = Store(path)
            model = revolved()
            saved = store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(model),
                    preserve=[],
                )
            )
            before = path.read_bytes()
            radius = model["features"][0]["vertices"][1]["x"]
            edit = dict(
                action="preview",
                expected_revision=1,
                operations=[dict(op="set_parameter", id=radius, mm="12")],
                preserve=[],
            )
            preview = store.execute(edit)
            self.assertNotEqual(
                preview["bodies"][0]["volume_mm3"], saved["bodies"][0]["volume_mm3"]
            )
            self.assertEqual(path.read_bytes(), before)
            changed = store.execute(
                {**edit, "action": "commit", "transaction_id": "edit"}
            )
            self.assertEqual(
                Store(path).execute(dict(action="inspect"))["model"], changed["model"]
            )
            bad = {
                **edit,
                "expected_revision": 2,
                "operations": [dict(op="set_parameter", id=radius, mm="-1")],
            }
            changed_bytes = path.read_bytes()
            self.assertIn(
                dispatch(store, bad)["error"]["code"],
                ["unsupported_revolution", "invalid_profile"],
            )
            self.assertEqual(path.read_bytes(), changed_bytes)
            undo = store.execute(
                dict(action="undo", expected_revision=2, transaction_id="undo")
            )
            self.assertEqual(undo["model"], saved["model"])


if __name__ == "__main__":
    unittest.main()
