import json
import math
from pathlib import Path
from fractions import Fraction
import tempfile
import unittest
from unittest.mock import patch
from document import Document, DocumentError, Feature


def planar():
    return (Document().append("base", "box", lo=[0, 0, 0], hi=[10, 10, 4])
            .append("tool", "box", lo=[2, 2, -1], hi=[4, 4, 5])
            .append("cut", "cut", left="base", right="tool"))


def curved():
    return (Document().append("base", "rectangle", bounds=[-5, -5, 5, 5], z=[0, 4])
            .append("tool", "cylinder", center=[0, 0], radius=1, z=[-1, 5])
            .append("cut", "cut", left="base", right="tool"))


class DocumentTests(unittest.TestCase):
    def test_planar_edit_replays_descendants_and_preserves_original(self):
        before = planar()
        after = before.replace("base", lo=[0, 0, 0], hi=[12, 10, 4])
        self.assertEqual(before.evaluate()["cut"].volume, 384)
        self.assertEqual(after.evaluate()["cut"].volume, 464)
        self.assertEqual([f.id for f in before.features], [f.id for f in after.features])

    def test_curved_edit_replays_descendants(self):
        before = curved()
        after = before.replace("tool", center=[0, 0], radius=2, z=[-1, 5])
        self.assertAlmostEqual(before.evaluate()["cut"].volume, 400 - 4 * math.pi)
        self.assertAlmostEqual(after.evaluate()["cut"].volume, 400 - 16 * math.pi)
        self.assertEqual(after.evaluate()["cut"].validate(), ())

    def test_exact_fraction_survives_json(self):
        d = Document().append("thin", "box", lo=[0, 0, 0], hi=["1/3", "1/7", "1/1000000000000000000000000000000"])
        restored = Document.from_json(d.to_json())
        self.assertEqual(restored.evaluate()["thin"].volume, Fraction(1, 21 * 10**30))

    def test_both_backends_share_document(self):
        d = planar().append("round", "cylinder", center=[20, 0], radius=2, z=[0, 3])
        restored = Document.from_json(d.to_json())
        self.assertEqual(restored.evaluate()["cut"].volume, 384)
        self.assertAlmostEqual(restored.evaluate()["round"].volume, 12 * math.pi)

    def test_mixed_boolean_rejected_without_mutation(self):
        d = planar().append("round", "cylinder", center=[0, 0], radius=1, z=[0, 4])
        original = d.to_json()
        with self.assertRaisesRegex(DocumentError, "Mixed-backend"):
            d.append("mixed", "cut", left="base", right="round")
        self.assertEqual(d.to_json(), original)

    def test_failed_downstream_rebuild_is_transactional(self):
        d = (curved().append("extra", "cylinder", center=[3, 0], radius=1, z=[-1, 5])
             .append("second", "cut", left="cut", right="extra"))
        original = d.to_json()
        with self.assertRaisesRegex(DocumentError, "tangency"):
            d.replace("extra", center=[2, 0], radius=1, z=[-1, 5])
        self.assertEqual(d.to_json(), original)

    def test_empty_result_is_valid(self):
        d = curved().append("empty", "cut", left="cut", right="cut")
        self.assertEqual(d.evaluate()["empty"].volume, 0)
        self.assertEqual(d.evaluate()["empty"].validate(), ())

    def test_undo_roundtrip(self):
        d = curved()
        self.assertEqual(Document.from_json(d.to_json()).undo().features, d.features[:-1])
        with self.assertRaises(DocumentError):
            Document().undo()

    def test_duplicate_id_and_forward_reference(self):
        with self.assertRaises(DocumentError):
            planar().append("base", "box", lo=[0, 0, 0], hi=[1, 1, 1])
        with self.assertRaises(DocumentError):
            Document().append("bad", "cut", left="future", right="future")

    def test_rejects_invalid_parameters(self):
        for bounds in ([0, 0, 0], [0, 0, 0, 1], [0, 0, True, 1], [0, 0, math.inf, 1]):
            with self.subTest(bounds=bounds), self.assertRaises(DocumentError):
                Document().append("bad", "rectangle", bounds=bounds, z=[0, 1])
        with self.assertRaises(DocumentError):
            Document().append("bad", "box", lo=[0, 0, 0], hi=[1.1, 1, 1])

    def test_rejects_unknown_fields_operations_units_and_schema(self):
        d = json.loads(curved().to_json())
        for key, value in (("units", "inch"), ("schema", "future"), ("extra", 1)):
            changed = dict(d, **{key: value})
            with self.assertRaises(DocumentError):
                Document.from_json(json.dumps(changed))
        with self.assertRaises(DocumentError):
            Document().append("bad", "execute", command="anything")
        with self.assertRaises(DocumentError):
            Document().append("bad", "box", lo=[0, 0, 0], hi=[1, 1, 1], extra=2)

    def test_rejects_duplicate_json_keys_and_nonfinite(self):
        for text in ('{"schema":1,"schema":2}', '{"x":NaN}', 'null', '[]', '{'):
            with self.subTest(text=text), self.assertRaises(DocumentError):
                Document.from_json(text)

    def test_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "model.json"
            curved().save(path)
            self.assertEqual(Document.load(path), curved())

    def test_failed_write_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "model.json"
            curved().save(path)
            original = path.read_bytes()
            with patch("document.os.replace", side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    planar().save(path)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(temp).iterdir()), [path])

    def test_invalid_model_cannot_overwrite_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "model.json"
            planar().save(path)
            original = path.read_bytes()
            bad = Document((Feature.make("bad", "cut", {"left": "missing", "right": "missing"}),))
            with self.assertRaises(DocumentError):
                bad.save(path)
            self.assertEqual(path.read_bytes(), original)

    def test_defensive_parameter_copy_and_readonly_results(self):
        d = planar()
        d.features[0].parameters["hi"][0] = 999
        self.assertEqual(d.evaluate()["base"].volume, 400)
        with self.assertRaises(TypeError):
            d.evaluate()["new"] = None

    def test_convex_prism(self):
        d = Document().append("wedge", "prism", polygon=[[0, 0], [4, 0], [0, 3]], height="1/3")
        self.assertEqual(d.evaluate()["wedge"].volume, 2)

    def test_union_and_intersection(self):
        for operation, expected in (("union", 408), ("intersection", 16)):
            d = planar().append("result", operation, left="base", right="tool")
            self.assertEqual(d.evaluate()["result"].volume, expected)

    def test_unknown_replacement_is_rejected(self):
        with self.assertRaises(DocumentError):
            planar().replace("unknown", lo=[0, 0, 0], hi=[1, 1, 1])

    def test_payload_limits(self):
        with self.assertRaises(DocumentError):
            Document.from_json(" " * (1024 * 1024 + 1))
        with self.assertRaises(DocumentError):
            Document(tuple(Feature.make("b" + str(i), "box", {"lo": [0,0,0], "hi": [1,1,1]})
                           for i in range(129))).evaluate()


if __name__ == "__main__":
    unittest.main()
