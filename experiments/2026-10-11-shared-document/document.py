"""Disposable shared editing/persistence probe. Geometry backends remain separate."""
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType
import json
import math
import os
import re
import sys
import tempfile

EXPERIMENTS = Path(__file__).resolve().parents[1]
for name in ("2026-10-11-boundary-kernel", "2026-10-11-cylinder-kernel", "2026-10-12-shared-topology"):
    sys.path.append(str(EXPERIMENTS / name))
from kernel import Solid
from boundary import Body as PlanarBody
from cylinders import Body as CurvedBody
from curves import Rect, Disk

SCHEMA = "fusion-research-document/1"
MAX_FEATURES = 128
MAX_BYTES = 1024 * 1024
BOOLEANS = {"cut", "union", "intersection"}
FIELDS = {
    "box": {"lo", "hi"},
    "prism": {"polygon", "height"},
    "rectangle": {"bounds", "z"},
    "cylinder": {"center", "radius", "z"},
    **{op: {"left", "right"} for op in BOOLEANS},
}


class DocumentError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise DocumentError(message)


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", value),
            "Feature IDs must be 1-64 letters, digits, underscores or hyphens")


def exact(value):
    require(type(value) in (int, str), "Exact geometry requires integers or rational strings")
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise DocumentError("Invalid rational coordinate") from error


def vector(value, size, rational=False):
    require(type(value) is list and len(value) == size, "Wrong coordinate vector size")
    if rational:
        return tuple(exact(x) for x in value)
    require(all(type(x) in (int, float) and math.isfinite(x) for x in value),
            "Analytic geometry requires finite numeric coordinates")
    return tuple(value)


@dataclass(frozen=True)
class Feature:
    id: str
    operation: str
    parameters_json: str

    @classmethod
    def make(cls, feature_id, operation, parameters):
        identifier(feature_id)
        require(isinstance(operation, str) and operation in FIELDS, "Unsupported operation")
        require(type(parameters) is dict and set(parameters) == FIELDS[operation],
                "Unexpected or missing operation parameters")
        try:
            text = json.dumps(parameters, sort_keys=True, allow_nan=False, separators=(",", ":"))
        except (ValueError, TypeError) as error:
            raise DocumentError("Parameters must be finite JSON values") from error
        require(len(text.encode()) <= MAX_BYTES // MAX_FEATURES, "Feature payload too large")
        return cls(feature_id, operation, text)

    @property
    def parameters(self):
        return json.loads(self.parameters_json)


@dataclass(frozen=True)
class Model:
    backend: str
    shape: object

    @property
    def volume(self):
        return self.shape.volume() if self.backend == "rational-planar" else self.shape.volume

    @property
    def area(self):
        return self.shape.boundary.area() if self.backend == "rational-planar" else self.shape.area

    def topology(self):
        from adapters import from_model
        return from_model(self.backend, self.shape)

    def validate(self):
        errors = (self.shape.boundary.validate() if self.backend == "rational-planar"
                  else self.shape.validate())
        if self.backend == "rational-planar" and self.shape.boundary.volume() != self.volume:
            errors = errors + ["Boundary/cell volume mismatch"]
        if not math.isfinite(float(self.volume)) or not math.isfinite(self.area):
            errors = errors + ["Nonfinite model measurement"]
        if self.volume < 0 or self.area < 0:
            errors = errors + ["Negative model measurement"]
        if not errors:
            try:
                errors = errors + list(self.topology().validate())
            except ValueError as error:
                errors = errors + ["Shared topology: " + str(error)]
        return tuple(sorted(set(errors)))

    def summary(self):
        if self.backend == "rational-planar":
            surfaces = {"planar_faces": len(self.shape.boundary.faces), "cylindrical_walls": 0}
        else:
            surfaces = {
                "planar_wall_patches": sum(w.edge.kind == "line" for w in self.shape.walls),
                "cylindrical_walls": sum(w.edge.kind == "arc" for w in self.shape.walls),
                "cap_regions": len(self.shape.caps),
            }
        return {"backend": self.backend, "volume_mm3": float(self.volume),
                "exact_volume_mm3": str(self.volume) if self.backend == "rational-planar" else None,
                "area_mm2": self.area, "surfaces": surfaces, "validation_errors": list(self.validate())}


def build(feature, models):
    p = feature.parameters
    op = feature.operation
    if op == "box":
        shape = PlanarBody.from_solid(Solid.box(vector(p["lo"], 3, True), vector(p["hi"], 3, True)))
        return Model("rational-planar", shape)
    if op == "prism":
        require(type(p["polygon"]) is list and 3 <= len(p["polygon"]) <= 64,
                "Prism requires 3-64 profile vertices")
        polygon = tuple(vector(v, 2, True) for v in p["polygon"])
        return Model("rational-planar", PlanarBody.from_solid(Solid.extrude(polygon, exact(p["height"]))))
    if op in ("rectangle", "cylinder"):
        z = vector(p["z"], 2)
        profile = Rect(*vector(p["bounds"], 4)) if op == "rectangle" else Disk(
            *vector(p["center"], 2), vector([p["radius"]], 1)[0])
        return Model("analytic-parallel", CurvedBody.extrude(profile, *z))
    left, right = p["left"], p["right"]
    identifier(left)
    identifier(right)
    require(left in models and right in models, "Operations may reference only earlier features")
    a, b = models[left], models[right]
    require(a.backend == b.backend, "Mixed-backend Booleans are unsupported; no implicit conversion")
    return Model(a.backend, getattr(a.shape, op)(b.shape))


@dataclass(frozen=True)
class Document:
    features: tuple = ()

    def evaluate(self):
        require(type(self.features) is tuple and len(self.features) <= MAX_FEATURES,
                "Invalid feature sequence")
        models = {}
        for feature in self.features:
            require(isinstance(feature, Feature), "Invalid feature record")
            checked = Feature.make(feature.id, feature.operation, feature.parameters)
            require(feature == checked, "Noncanonical feature record")
            require(feature.id not in models, "Duplicate feature ID")
            try:
                model = build(feature, models)
                errors = model.validate()
                require(not errors, "; ".join(errors))
            except (ValueError, TypeError, OverflowError, ArithmeticError) as error:
                raise DocumentError("Feature " + feature.id + ": " + str(error)) from error
            models[feature.id] = model
        return MappingProxyType(models)

    def append(self, feature_id, operation, **parameters):
        candidate = Document(self.features + (Feature.make(feature_id, operation, parameters),))
        candidate.evaluate()
        return candidate

    def replace(self, feature_id, **parameters):
        require(any(f.id == feature_id for f in self.features), "Unknown feature ID")
        candidate = Document(tuple(Feature.make(f.id, f.operation, parameters) if f.id == feature_id
                                   else f for f in self.features))
        candidate.evaluate()
        return candidate

    def undo(self):
        require(bool(self.features), "Nothing to undo")
        return Document(self.features[:-1])

    def to_json(self):
        self.evaluate()
        return json.dumps({"schema": SCHEMA, "units": "mm", "features": [
            {"id": f.id, "operation": f.operation, "parameters": f.parameters} for f in self.features
        ]}, indent=2, allow_nan=False) + "\n"

    @classmethod
    def from_json(cls, text):
        require(isinstance(text, str) and len(text.encode()) <= MAX_BYTES, "Document payload too large")
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                require(key not in result, "Duplicate JSON key")
                result[key] = value
            return result
        try:
            data = json.loads(text, object_pairs_hook=unique_pairs,
                              parse_constant=lambda _: (_ for _ in ()).throw(DocumentError("Nonfinite JSON")))
        except (ValueError, RecursionError) as error:
            raise DocumentError("Invalid document JSON: " + str(error)) from error
        require(type(data) is dict and set(data) == {"schema", "units", "features"},
                "Unexpected document fields")
        require(data["schema"] == SCHEMA and data["units"] == "mm", "Unsupported schema or units")
        records = data["features"]
        require(type(records) is list and len(records) <= MAX_FEATURES, "Invalid feature list")
        features = []
        for item in records:
            require(type(item) is dict and set(item) == {"id", "operation", "parameters"},
                    "Unexpected feature fields")
            features.append(Feature.make(item["id"], item["operation"], item["parameters"]))
        result = cls(tuple(features))
        result.evaluate()
        return result

    def save(self, path):
        """Validate/replay before same-directory atomic replacement; no partial saved document."""
        text = self.to_json()
        require(len(text.encode()) <= MAX_BYTES, "Document payload too large")
        path = Path(path)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix="." + path.name + ".", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    @classmethod
    def load(cls, path):
        with open(path, "rb") as handle:
            payload = handle.read(MAX_BYTES + 1)
        require(len(payload) <= MAX_BYTES, "Document payload too large")
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise DocumentError("Document must be UTF-8") from error
        return cls.from_json(text)
