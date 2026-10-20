"""Linked planar material patterns: repeated exact union, not assembly identity."""

from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest
from store import Store, CadError, evaluate
from topology import topology_model
from measurements import measure_model
from test_intersection import rectangle, operations
from test_planar_shell import shell
from test_frustum import frustum


def pattern(model=None, count=3, step=(50, 0, 0)):
    model = model or rectangle("part", 0, 0, 40, 30, 20)
    model["parameters"].update(
        {"step." + axis: str(value) for axis, value in zip("xyz", step)}
    )
    model["features"].append(
        dict(
            kind="linear_pattern",
            id="pattern",
            input=model["features"][-1]["id"],
            count=count,
            step=["step." + a for a in "xyz"],
        )
    )
    return model


class LinearPattern(unittest.TestCase):
    def test_separated_touching_overlapping_and_negative_steps(self):
        for count, step, volume, components in [
            (3, (50, 0, 0), 72000, 3),
            (3, (40, 0, 0), 72000, 1),
            (3, (20, 0, 0), 48000, 1),
            (3, (-50, 0, 0), 72000, 3),
            (1, (0, 0, 0), 24000, 1),
            (16, (50, 0, 0), 384000, 16),
        ]:
            with self.subTest(count=count, step=step):
                model = pattern(count=count, step=step)
                body = evaluate(model)["bodies"][0]
                self.assertEqual(F(body["volume_mm3"]), volume)
                self.assertEqual(len(body["components"]), components)
                center = measure_model(model, "pattern")["centroid_mm"]
                self.assertEqual(
                    list(map(F, center)), [20 + F(count - 1, 2) * step[0], 15, 10]
                )
                self.assertEqual(
                    len(topology_model(model, "pattern")["shells"]), components
                )

    def test_hollow_material_source_and_derived_spacing(self):
        model = pattern(shell(), 3, (50, 0, 0))
        self.assertEqual(F(evaluate(model)["bodies"][0]["volume_mm3"]), 3 * 7152)
        model["relations"] = {"step.x": dict(offset_mm="10", terms={"part.c1": "1"})}
        result = evaluate(model, [dict(op="set_parameter", id="part.c1", mm="50")])
        self.assertEqual(result["model"]["parameters"]["step.x"], "60")
        self.assertEqual(
            F(result["bodies"][0]["volume_mm3"]), 3 * (50 * 30 * 20 - 46 * 26 * 18)
        )

    def test_invalid_counts_steps_curves_and_nonmanifold_touch_reject(self):
        for model, code in [
            (pattern(count=0), "pattern_count"),
            (pattern(count=17), "pattern_count"),
            (pattern(step=(0, 0, 0)), "pattern_step"),
            (pattern(step=(600000, 0, 0)), "pattern_range"),
            (pattern(frustum()), "unsupported_reference"),
        ]:
            with self.subTest(code=code), self.assertRaises(CadError) as caught:
                evaluate(model)
            self.assertEqual(caught.exception.detail["code"], code)
        with self.assertRaises(CadError):
            evaluate(pattern(count=2, step=(40, 30, 0)))

    def test_count_spacing_history_and_consumed_input(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "part.json")
            made = store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="create",
                    operations=operations(pattern()),
                    preserve=[],
                )
            )
            model = made["model"]
            feature = {**model["features"][-1], "count": 2}
            edit = dict(
                expected_revision=1,
                operations=[
                    dict(op="replace_feature", id="pattern", feature=feature),
                    dict(op="set_parameter", id="step.x", mm="40"),
                ],
                preserve=[],
            )
            before = store.path.read_bytes()
            result = store.execute(dict(action="preview", **edit))
            self.assertEqual(result["bodies"][0]["volume_mm3"], "48000")
            self.assertEqual(store.path.read_bytes(), before)
            store.execute(dict(action="commit", transaction_id="edit", **edit))
            self.assertEqual(
                Store(store.path).execute(
                    dict(action="undo", expected_revision=2, transaction_id="undo")
                )["bodies"],
                made["bodies"],
            )
        model = pattern()
        model["features"].append(
            dict(
                kind="linear_pattern",
                id="second",
                input="part",
                count=2,
                step=["step.x", "step.y", "step.z"],
            )
        )
        with self.assertRaises(CadError) as caught:
            evaluate(model)
        self.assertEqual(caught.exception.detail["code"], "unsupported_branch")
