"""Symbolic pi moments, blind floors, asymmetric holes and placed engineering values."""

import ast
from fractions import Fraction as F
import math
import unittest
from measurements import measure_model
from test_round_stock import cylinder, flange
from test_holes import perforated
from test_blind_holes import blind
from test_polyhedral_transforms import moved, turned, rotated
from test_instances import instance


def exact_value(expression, pi=math.pi):
    """Interpret only the documented numeric/pi arithmetic, never executable Python."""

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return F(node.value)
        if isinstance(node, ast.Name) and node.id == "pi":
            return pi
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -visit(node.operand)
        if isinstance(node, ast.BinOp):
            a, b = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add):
                return a + b
            if isinstance(node.op, ast.Sub):
                return a - b
            if isinstance(node.op, ast.Mult):
                return a * b
            if isinstance(node.op, ast.Div):
                return a / b
        raise ValueError("Unsupported exact expression")

    return visit(ast.parse(expression, mode="eval").body)


def measure(model):
    return measure_model(model, model["features"][-1]["id"])


class AnalyticMeasurements(unittest.TestCase):
    def test_cylinder_closed_form_and_rational_symbolic_simplification(self):
        result = measure(cylinder(cx="2", cy="-3", radius="4", height="5"))
        self.assertEqual(result["centroid_mm"], ["2", "-3", "5/2"])
        self.assertEqual(result["bounds_mm"], [["-2", "-7", "0"], ["6", "1", "5"]])
        self.assertEqual(
            result["centroidal_volume_inertia_mm5"],
            [
                ["(1460/3)*pi", "0", "0"],
                ["0", "(1460/3)*pi", "0"],
                ["0", "0", "(640)*pi"],
            ],
        )
        # Independent removed-cylinder first moments, with common pi cancelled.
        result = measure(blind(flange()))
        self.assertEqual(
            result["centroid_mm"],
            ["0", "0", str((F(8000) * F(5, 2) - F(236) * 4) / 7764)],
        )

    def test_asymmetric_blind_holes_exact_first_moments_and_cross_inertia(self):
        model = blind(perforated())
        result = measure(model)
        # Four exact substitutions verify the bounded rational functions, beyond rounding at pi.
        for pi in [F(1), F(2), F(3), F(22, 7)]:
            volume = 36000 - 36 * pi
            cy = (1080000 - 432 * pi) / volume
            cz = (108000 - 180 * pi) / volume
            self.assertEqual(
                [exact_value(x, pi) for x in result["centroid_mm"]], [F(50), cy, cz]
            )
            yz = F(36000) * 30 * 3 - 36 * pi * 12 * 5
            expected_yz = -(yz - volume * cy * cz)
            self.assertEqual(
                exact_value(result["centroidal_volume_inertia_mm5"][1][2], pi),
                expected_yz,
            )
        reversed_result = measure(blind(perforated(True)))
        self.assertEqual(result, reversed_result)
        through = measure(perforated())
        self.assertEqual(through["centroid_mm"][2], "3")
        self.assertEqual(through["centroidal_volume_inertia_mm5"][1][2], "0")

    def test_fractional_placement_preserves_tensor_and_rotates_centroid_and_bounds(
        self,
    ):
        model = blind(perforated())
        original = measure(model)
        delta = (F(7, 3), F(-2, 5), F(9, 7))
        pivot = (F(1, 3), F(2, 5), F(-3, 7))
        for placed in [moved(model, delta), instance(model, offset=delta)]:
            actual = measure(placed)
            self.assertEqual(
                actual["centroidal_volume_inertia_mm5"],
                original["centroidal_volume_inertia_mm5"],
            )
            for pi in [F(2), F(3), F(22, 7), F(355, 113)]:
                self.assertEqual(
                    [exact_value(c, pi) for c in actual["centroid_mm"]],
                    [
                        exact_value(c, pi) + d
                        for c, d in zip(original["centroid_mm"], delta)
                    ],
                )
        for axis in "xyz":
            for turns in (1, 2, 3):
                actual = measure(turned(model, axis, turns, pivot))
                center = [exact_value(c) for c in original["centroid_mm"]]
                expected = rotated(center, axis, turns, tuple(map(float, pivot)))
                for a, b in zip(actual["centroid_mm"], expected):
                    self.assertAlmostEqual(exact_value(a), float(b), places=10)
                vectors = [
                    rotated(
                        tuple(F(int(i == j)) for i in range(3)), axis, turns, (0, 0, 0)
                    )
                    for j in range(3)
                ]
                matrix = [[vectors[j][i] for j in range(3)] for i in range(3)]
                for pi in [F(2), F(3), F(22, 7), F(355, 113)]:
                    tensor = [
                        [exact_value(v, pi) for v in row]
                        for row in original["centroidal_volume_inertia_mm5"]
                    ]
                    for i in range(3):
                        for j in range(3):
                            expected = sum(
                                matrix[i][a] * tensor[a][b] * matrix[j][b]
                                for a in range(3)
                                for b in range(3)
                            )
                            self.assertEqual(
                                exact_value(
                                    actual["centroidal_volume_inertia_mm5"][i][j], pi
                                ),
                                expected,
                            )
                corners = [(x, y, z) for x in (0, 100) for y in (0, 60) for z in (0, 6)]
                transformed = [rotated(p, axis, turns, pivot) for p in corners]
                self.assertEqual(
                    actual["bounds_mm"],
                    [
                        [str(min(p[i] for p in transformed)) for i in range(3)],
                        [str(max(p[i] for p in transformed)) for i in range(3)],
                    ],
                )


if __name__ == "__main__":
    unittest.main()
