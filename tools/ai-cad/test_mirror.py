"""Exact rational-plane reflection, orientation, dependencies and safe edits."""

from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest
from store import Store, CadError, evaluate
from measurements import measure_model
from topology import topology_model
from exports import tessellate
from test_holes import audit_triangles
from test_intersection import rectangle, operations
from test_planar_shell import shell
from test_linear_pattern import pattern
from test_frustum import frustum


def mirror(model=None, normal=(1, 0, 0), offset="50", keep=False, id="mirror"):
    model = model or rectangle("part", 0, 0, 40, 30, 20)
    model["parameters"][id + ".offset"] = offset
    model["features"].append(
        dict(
            kind="mirror_plane",
            id=id,
            input=model["features"][-1]["id"],
            normal=list(map(str, normal)),
            offset=id + ".offset",
            keep_original=keep,
        )
    )
    return model


def reflected(point, normal, offset):
    point, normal = list(map(F, point)), list(map(F, normal))
    scale = (
        2
        * (sum(a * b for a, b in zip(point, normal)) - F(offset))
        / sum(v * v for v in normal)
    )
    return [p - scale * n for p, n in zip(point, normal)]


class Mirror(unittest.TestCase):
    def test_all_axes_oblique_planes_and_normal_scaling(self):
        for normal, offset in [
            ((1, 0, 0), 50),
            ((0, 1, 0), -10),
            ((0, 0, 1), 0),
            ((1, 2, 3), F(7, 3)),
            ((-2, -4, -6), F(-14, 3)),
            ((F(1, 10**30), 0, 0), 0),
        ]:
            with self.subTest(normal=normal):
                model = mirror(normal=normal, offset=str(offset))
                self.assertEqual(evaluate(model)["bodies"][0]["volume_mm3"], "24000")
                self.assertEqual(
                    list(map(F, measure_model(model, "mirror")["centroid_mm"])),
                    reflected((20, 15, 10), normal, offset),
                )
                self.assertEqual(len(topology_model(model, "mirror")["shells"]), 1)
                mesh = tessellate(model, "mirror", 32, True)
                self.assertAlmostEqual(
                    audit_triangles(
                        [
                            [tuple(mesh["vertices"][i]) for i in t]
                            for t in mesh["triangles"]
                        ],
                        0,
                    ),
                    24000,
                )

    def test_involution_hollow_disconnected_and_source_retention(self):
        for source in [shell(), pattern()]:
            original = evaluate(source)["bodies"][0]
            model = mirror(source, normal=(1, 2, 3), offset="7/3", keep=True)
            bodies = evaluate(model)["bodies"]
            self.assertEqual(len(bodies), 2)
            self.assertIn(original, bodies)
            first = next(b for b in bodies if b["feature_id"] == "mirror")
            self.assertEqual(first["volume_mm3"], original["volume_mm3"])
            model = mirror(model, normal=(1, 2, 3), offset="7/3", id="again")
            returned = next(
                b for b in evaluate(model)["bodies"] if b["feature_id"] == "again"
            )
            self.assertEqual(
                sorted(map(tuple, returned["boundary"]["vertices"])),
                sorted(map(tuple, original["boundary"]["vertices"])),
            )
            self.assertEqual(
                measure_model(model, "again")["centroid_mm"],
                measure_model(model, original["feature_id"])["centroid_mm"],
            )

    def test_revision_history_plane_replacement_and_atomic_bad_normal(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "part.json")
            made = store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(mirror(keep=True)),
                    preserve=[],
                )
            )
            feature = {
                **made["model"]["features"][-1],
                "normal": ["1", "1", "0"],
                "keep_original": False,
            }
            edit = dict(
                expected_revision=1,
                operations=[dict(op="replace_feature", id="mirror", feature=feature)],
                preserve=[],
            )
            before = store.path.read_bytes()
            self.assertEqual(
                len(store.execute(dict(action="preview", **edit))["bodies"]), 1
            )
            self.assertEqual(store.path.read_bytes(), before)
            store.execute(dict(action="commit", transaction_id="replace", **edit))
            changed = store.path.read_bytes()
            feature["normal"] = ["0", "0", "0"]
            with self.assertRaises(CadError) as caught:
                store.execute(
                    dict(
                        action="commit",
                        expected_revision=2,
                        transaction_id="bad",
                        operations=[
                            dict(op="replace_feature", id="mirror", feature=feature)
                        ],
                        preserve=[],
                    )
                )
            self.assertEqual(caught.exception.detail["code"], "mirror_normal")
            self.assertEqual(store.path.read_bytes(), changed)
            self.assertEqual(
                Store(store.path).execute(
                    dict(action="undo", expected_revision=2, transaction_id="undo")
                )["bodies"],
                made["bodies"],
            )
        with self.assertRaises(CadError):
            evaluate(mirror(frustum()))
