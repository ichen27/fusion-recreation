"""Simultaneous exact constraints compile to editable affine dependencies."""

import copy
from fractions import Fraction as F
from pathlib import Path
import random
import tempfile
import unittest
from store import CadError, Store, evaluate
from test_relations import model, relation, set_value


def equation(id, terms, offset=0):
    return dict(
        id=id, terms={k: str(v) for k, v in terms.items() if v}, offset_mm=str(offset)
    )


def constrain(targets, equations):
    return dict(op="constrain_linear", targets=targets, equations=equations)


def dimensions():
    return constrain(
        ["left", "right"],
        [
            equation("span", {"left": 1, "right": 1, "gap": 1, "span": -1}),
            equation("ratio", {"left": 1, "right": -2}),
        ],
    )


def source():
    m = model(
        dict(
            span=100, gap=10, left=60, right=30, offset=70, depth=10, height=20, zero=0
        )
    )
    m["features"] = [
        dict(
            kind="block", id="left_part", width="left", depth="depth", height="height"
        ),
        dict(
            kind="block", id="right_part", width="right", depth="depth", height="height"
        ),
        dict(
            kind="translate",
            id="right_placed",
            input="right_part",
            offset=["offset", "zero", "zero"],
        ),
    ]
    return evaluate(m, [relation("offset", {"left": 1, "gap": 1})])["model"]


def source_operations():
    from test_intersection import operations

    m = source()
    return operations(m) + [
        dict(op="set_relation", id=id, relation=value)
        for id, value in m["relations"].items()
    ]


class LinearConstraints(unittest.TestCase):
    def error(self, m, ops, code, preserve=None):
        with self.assertRaises(CadError) as caught:
            evaluate(m, ops, preserve)
        self.assertEqual(caught.exception.detail["code"], code)
        return caught.exception.detail

    def test_coupled_rules_regenerate_native_parts_and_expose_existing_provenance(self):
        m = evaluate(source(), [dimensions()])["model"]
        self.assertEqual(
            m["relations"]["left"],
            dict(offset_mm="0", terms={"gap": "-2/3", "span": "2/3"}),
        )
        changed = evaluate(m, [set_value("span", 130)], ["gap", "depth", "height"])
        self.assertEqual(
            {k: changed["model"]["parameters"][k] for k in ("left", "right", "offset")},
            dict(left="80", right="40", offset="90"),
        )
        self.assertEqual(
            [b["volume_mm3"] for b in changed["bodies"]], ["16000", "8000"]
        )
        self.assertEqual(
            changed["changed_parameters"], ["left", "offset", "right", "span"]
        )
        self.error(m, [set_value("left", 90)], "derived_parameter")
        self.error(m, [set_value("span", 130)], "preserve_conflict", ["left"])
        fixed = evaluate(m, [dict(op="fix_parameter", id="left")])["model"]
        self.error(fixed, [set_value("span", 130)], "constraint_conflict")
        frozen = evaluate(m, [dict(op="remove_relation", id="left")])["model"]
        self.assertEqual(
            evaluate(frozen, [set_value("span", 130)])["model"]["parameters"]["left"],
            "60",
        )
        damaged = copy.deepcopy(m)
        damaged["parameters"]["left"] = "59"
        self.error(damaged, [], "relation_mismatch")

    def test_redundant_equations_order_independence_and_existing_derived_inputs(self):
        m = model(dict(x=0, y=0, a=9, b=3, driver=9))
        rows = [
            equation("sum", dict(x=1, y=1, a=-1)),
            equation("difference", dict(x=1, y=-1, b=-1)),
            equation("redundant", dict(x=2, y=2, a=-2)),
        ]
        first = evaluate(m, [constrain(["x", "y"], rows)])["model"]
        second = evaluate(m, [constrain(["y", "x"], list(reversed(rows)))])["model"]
        self.assertEqual(first, second)
        chained = evaluate(
            first, [relation("a", {"driver": 1}), set_value("driver", 15)]
        )["model"]
        self.assertEqual(
            (chained["parameters"]["x"], chained["parameters"]["y"]), ("9", "6")
        )
        self.error(first, [relation("a", {"x": 1})], "relation_cycle")
        replacement = constrain(["x"], [equation("new", dict(x=1, driver=-2), 1)])
        self.assertEqual(
            evaluate(first, [replacement])["model"]["parameters"]["x"], "19"
        )

    def test_rank_conflict_and_driver_only_conditions_are_not_silently_solved_at_current_values(
        self,
    ):
        m = model(dict(x=0, y=0, a=4, b=4))
        rows = [equation("sum", dict(x=1, y=1), 3)]
        detail = self.error(m, [constrain(["x", "y"], rows)], "linear_underdetermined")
        self.assertIn("Rank 1 for 2", detail["message"])
        conflict = rows + [equation("conflict", dict(x=2, y=2), 7)]
        detail = self.error(m, [constrain(["x", "y"], conflict)], "linear_inconsistent")
        self.assertIn("conflict", detail["message"])
        # a==b happens today, but preserving both constraints would restrict future drivers.
        self.error(
            m,
            [
                constrain(
                    ["x"],
                    [equation("a", dict(x=1, a=-1)), equation("b", dict(x=1, b=-1))],
                )
            ],
            "linear_driver_constraint",
        )

    def test_validation_limits_and_intermediate_overflow(self):
        m = model(dict(x=0, y=0, a=1))
        good = equation("eq", dict(x=1, a=-1))
        for op, code in [
            (constrain([], [good]), "linear_limit"),
            (constrain(["x"], []), "linear_limit"),
            (constrain(["x", "x"], [good]), "duplicate_id"),
            (constrain(["x"], [good, good]), "duplicate_id"),
            (constrain(["missing"], [good]), "missing_parameter"),
            (
                constrain(["x"], [equation("eq", dict(x=1, missing=1))]),
                "missing_parameter",
            ),
            (
                constrain(["x"], [dict(id="eq", terms=dict(x="0"), offset_mm="0")]),
                "invalid_linear_equation",
            ),
            (
                constrain(["x"], [dict(id="eq", terms=dict(x="1"), offset_mm="0.5")]),
                "invalid_number",
            ),
            (
                constrain(
                    ["x", "y"],
                    [
                        equation("a", dict(x=2**100, y=1)),
                        equation("b", dict(x=1, y=-(2**100))),
                    ],
                ),
                "linear_overflow",
            ),
        ]:
            with self.subTest(op=op):
                self.error(m, [op], code)
        m = model(
            {**{f"x{i}": 0 for i in range(10)}, **{f"a{i}": 1 for i in range(10)}}
        )
        rows = [
            equation(
                f"e{i}",
                {f"x{i}": 1, f"a{i}": -1, **({f"x{i + 1}": -1} if i < 9 else {})},
            )
            for i in range(10)
        ]
        self.error(m, [constrain([f"x{i}" for i in range(10)], rows)], "linear_limit")

    def test_seeded_symbolic_systems_satisfy_every_original_equation_after_driver_edits(
        self,
    ):
        rng = random.Random(6207)
        for case in range(40):
            # Strictly diagonally dominant matrices are nonsingular. Start from
            # independently chosen affine solutions and derive the input equations.
            a = [[F(rng.randint(-3, 3)) for _ in range(3)] for _ in range(3)]
            for i in range(3):
                a[i][i] = 1 + sum(abs(a[i][j]) for j in range(3) if i != j)
            solutions = [
                [F(rng.randint(-9, 9), rng.randint(1, 7)) for _ in range(3)]
                for _ in range(3)
            ]
            equations = []
            for i in range(3):
                terms = {f"x{j}": a[i][j] for j in range(3)}
                for k, name in enumerate(("u", "v")):
                    terms[name] = -sum(a[i][j] * solutions[j][k] for j in range(3))
                offset = sum(a[i][j] * solutions[j][2] for j in range(3))
                equations.append(equation(f"row{i}", terms, offset))
            m = model(dict(x0=0, x1=0, x2=0, u=3, v=-4))
            solved = evaluate(m, [constrain(["x0", "x1", "x2"], equations)])["model"]
            edited = evaluate(
                solved, [set_value("u", F(7, 11)), set_value("v", F(-3, 13))]
            )["model"]
            for current in (solved, edited):
                values = {k: F(v) for k, v in current["parameters"].items()}
                for j in range(3):
                    self.assertEqual(
                        values[f"x{j}"],
                        solutions[j][0] * values["u"]
                        + solutions[j][1] * values["v"]
                        + solutions[j][2],
                        case,
                    )
                for e in equations:
                    self.assertEqual(
                        sum(F(c) * values[k] for k, c in e["terms"].items()),
                        F(e["offset_mm"]),
                        case,
                    )

    def test_failed_constraints_are_atomic_and_compiled_rules_survive_reopen_undo(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.cad.json"
            store = Store(path)
            store.execute(
                dict(
                    action="commit",
                    expected_revision=0,
                    transaction_id="source",
                    operations=source_operations(),
                    preserve=[],
                )
            )
            store.execute(
                dict(
                    action="commit",
                    expected_revision=1,
                    transaction_id="solve",
                    operations=[dimensions()],
                    preserve=[],
                )
            )
            before = path.read_bytes()
            bad = constrain(["left", "right"], [equation("sum", dict(left=1, right=1))])
            with self.assertRaises(CadError):
                store.execute(
                    dict(
                        action="commit",
                        expected_revision=2,
                        transaction_id="bad",
                        operations=[bad],
                        preserve=[],
                    )
                )
            self.assertEqual(path.read_bytes(), before)
            store.execute(
                dict(
                    action="commit",
                    expected_revision=2,
                    transaction_id="wider",
                    operations=[set_value("span", 130)],
                    preserve=["gap"],
                )
            )
            reopened = Store(path).execute(dict(action="inspect"))
            self.assertEqual(reopened["model"]["parameters"]["right"], "40")
            self.assertEqual(reopened["model"]["parameters"]["offset"], "90")
            undo = store.execute(
                dict(action="undo", expected_revision=3, transaction_id="undo")
            )
            self.assertEqual(undo["model"]["parameters"]["right"], "30")
            self.assertIn("left", undo["model"]["relations"])
