"""Linked instances preserve source identity, independent placement and native edits."""

import copy
from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest
from store import CadError, Store, evaluate
from intent import explain_model
from test_intersection import rectangle, operations
from test_concave_operations import l_shape
from test_booleans import cases
from test_polyhedral_transforms import points, turned


def instance(model, source=None, name="copy", offset=(20, 0, 0)):
    model = copy.deepcopy(model)
    source = source or model["features"][-1]["id"]
    ids = [name + "." + axis for axis in "xyz"]
    model["parameters"].update({k: str(v) for k, v in zip(ids, offset)})
    model["features"].append(dict(kind="instance", id=name, source=source, offset=ids))
    return model


def bodies(model):
    return {b["feature_id"]: b for b in evaluate(model)["bodies"]}


class Instances(unittest.TestCase):
    def test_multiple_and_nested_copies_keep_source_and_follow_shared_dimensions(self):
        base = rectangle("part", 0, 0, 10, 4, 2)
        source = base["features"][-1]["id"]
        model = instance(instance(base, source, "left"), source, "right", (-20, 0, 0))
        model = instance(model, "left", "nested", (0, 10, 0))
        original = bodies(model)
        self.assertEqual(set(original), {source, "left", "right", "nested"})
        self.assertEqual({b["volume_mm3"] for b in original.values()}, {"80"})
        self.assertEqual(
            points(original["nested"]),
            {(x, y + 10, z) for x, y, z in points(original["left"])},
        )
        # Editing the extrusion height propagates through both direct and nested links.
        height = base["features"][-1]["height"]
        model["parameters"][height] = "3"
        self.assertEqual({b["volume_mm3"] for b in bodies(model).values()}, {"120"})
        info = explain_model(model, "nested")
        self.assertEqual(
            [f["id"] for f in info["source_features"]][-2:], ["left", "nested"]
        )
        self.assertEqual(
            set(info["parameters"][height]["affected_bodies"]), set(original)
        )
        before_move = bodies(model)
        model["parameters"]["left.x"] = "25"
        edited = bodies(model)
        self.assertEqual(edited["right"], before_move["right"])
        self.assertEqual(edited[source], before_move[source])
        self.assertEqual(
            points(edited["nested"]),
            {(x + 5, y, z) for x, y, z in points(before_move["nested"])},
        )

    def test_nonconvex_cavity_and_split_sources_retain_topology_and_downstream_operations(
        self,
    ):
        for model in [
            l_shape(),
            *[cases()[n][0] for n in ("through", "cavity", "split")],
        ]:
            source = model["features"][-1]["id"]
            original = bodies(model)[source]
            placed = instance(model, source, offset=(F(1, 3), -2, 5))
            result = bodies(placed)
            self.assertEqual(result[source], original)
            self.assertEqual(result["copy"]["volume_mm3"], original["volume_mm3"])
            self.assertEqual(
                len(result["copy"]["components"]), len(original.get("components", [1]))
            )
            turned_model = turned(placed, "x", 1)
            self.assertEqual(set(bodies(turned_model)), {source, "turned"})
            # A source remains available for a normal consuming feature after copies exist.
            turned_model["features"].append(
                dict(
                    kind="boolean",
                    id="joined",
                    left=source,
                    right="turned",
                    operation="union",
                )
            )
            final = bodies(turned_model)["joined"]
            self.assertTrue(F(final["volume_mm3"]) > 0)

    def test_references_cycles_and_unsupported_geometry_reject(self):
        base = instance(l_shape())
        for source in ("copy", "future", "l.profile"):
            model = copy.deepcopy(base)
            model["features"][-1]["source"] = source
            with self.assertRaises(CadError):
                evaluate(model)
        # Historical source selection is explicit: copying remains valid after it was consumed.
        model = turned(l_shape())
        model = instance(model, "l")
        self.assertEqual(set(bodies(model)), {"turned", "copy"})
        model = dict(
            parameters=dict(z="0", r="2", h="5"),
            fixed={},
            features=[
                dict(kind="cylinder", id="round", x="z", y="z", radius="r", height="h")
            ],
        )
        self.assertEqual(set(bodies(instance(model))), {"round", "copy"})

    def test_atomic_limits_source_deletion_undo_reopen_and_fixed_offsets(self):
        model = instance(l_shape())
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "part.json")
            original = store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(model),
                    preserve=[],
                )
            )
            before = store.path.read_bytes()
            for op in [
                dict(op="remove_feature", id="l"),
                dict(op="set_parameter", id="copy.x", mm="1000001"),
            ]:
                with self.assertRaises(CadError):
                    store.execute(
                        dict(
                            action="commit",
                            expected_revision=1,
                            transaction_id="invalid",
                            operations=[op],
                            preserve=[],
                        )
                    )
                self.assertEqual(store.path.read_bytes(), before)
            saved = store.execute(
                dict(
                    action="commit",
                    expected_revision=1,
                    transaction_id="move",
                    operations=[dict(op="set_parameter", id="copy.x", mm="30")],
                    preserve=[],
                )
            )
            self.assertEqual(
                next(b for b in saved["bodies"] if b["feature_id"] == "l"),
                next(b for b in original["bodies"] if b["feature_id"] == "l"),
            )
            undo = store.execute(
                dict(action="undo", expected_revision=2, transaction_id="undo")
            )
            self.assertEqual(undo["bodies"], original["bodies"])
            self.assertEqual(
                Store(store.path).execute(dict(action="inspect"))["bodies"],
                original["bodies"],
            )
        model["fixed"]["copy.x"] = "20"
        with self.assertRaises(CadError):
            evaluate(model, [dict(op="set_parameter", id="copy.x", mm="25")])


if __name__ == "__main__":
    unittest.main()
