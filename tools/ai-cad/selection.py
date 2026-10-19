"""Revision-bound workspace selection shared by the browser and MCP process.

Selection is a disposable sidecar, never part of native model history/exports.
The document lock serializes selection with model edits across processes.
"""

import hashlib
import json
import os
import tempfile
from store import BINARY, CadError, encode
from topology import topology_model


class Selection:
    def __init__(self, store):
        self.store = store
        self.path = store.path.with_suffix(store.path.suffix + ".selection.json")

    def _read(self):
        try:
            with self.path.open("rb") as stream:
                data = stream.read(4097)
        except FileNotFoundError:
            return None
        try:
            value = json.loads(data)
            if (
                len(data) > 4096
                or not isinstance(value, dict)
                or set(value)
                not in (
                    {"schema_version", "revision", "document_hash", "feature_id"},
                    {
                        "schema_version",
                        "revision",
                        "document_hash",
                        "feature_id",
                        "surface_id",
                    },
                )
                or type(value["schema_version"]) is not int
                or value["schema_version"] != (2 if "surface_id" in value else 1)
                or (
                    "surface_id" in value
                    and (
                        not isinstance(value["surface_id"], str)
                        or not isinstance(value["feature_id"], str)
                    )
                )
                or type(value["revision"]) is not int
                or not isinstance(value["document_hash"], str)
                or len(value["document_hash"]) != 64
                or not isinstance(value["feature_id"], (str, type(None)))
            ):
                raise ValueError("Invalid selection fields")
            return value
        except (ValueError, TypeError) as exc:
            raise CadError(
                "invalid_selection",
                "Workspace selection is damaged; clear or reselect a body",
            ) from exc

    def _write(self, value):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.path.parent, prefix=".selection-", delete=False
            ) as stream:
                temporary = stream.name
                stream.write(encode(value))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def execute(self, command):
        if not isinstance(command, dict):
            raise CadError("invalid_command", "Expected an object")
        action = command.get("action")
        if not (
            action == "context"
            and set(command) == {"action"}
            or action == "select"
            and set(command) == {"action", "expected_revision", "feature_id"}
            or action == "select_surface"
            and set(command)
            == {"action", "expected_revision", "feature_id", "surface_id"}
        ):
            raise CadError(
                "invalid_command", "Expected context or revision-bound select"
            )
        with self.store.locked():
            state = self.store.load()
            fingerprint = hashlib.sha256(encode(state)).hexdigest()
            result = self.store.inspect_model(state["model"])
            bodies = {b["feature_id"]: b for b in result["bodies"]}
            surface = None
            if action in ("select", "select_surface"):
                if (
                    type(command["expected_revision"]) is not int
                    or command["expected_revision"] != state["revision"]
                ):
                    raise CadError(
                        "revision_conflict", "Refresh the saved model before selecting"
                    )
                feature = command["feature_id"]
                if feature is not None and (
                    not isinstance(feature, str) or feature not in bodies
                ):
                    raise CadError("missing_body", "Select a terminal saved solid")
                selection = {
                    "schema_version": 1,
                    "revision": state["revision"],
                    "document_hash": fingerprint,
                    "feature_id": feature,
                }
                if action == "select_surface":
                    surface = self._surface(
                        result["model"], feature, command["surface_id"]
                    )
                    selection.update(schema_version=2, surface_id=command["surface_id"])
                self._write(selection)
            else:
                selection = self._read()
            status, body = "empty", None
            if selection and selection["feature_id"] is not None:
                if (
                    selection["revision"] != state["revision"]
                    or selection["document_hash"] != fingerprint
                ):
                    status = "stale"
                elif selection["feature_id"] not in bodies:
                    raise CadError(
                        "invalid_selection",
                        "Selected body is not a terminal saved solid",
                    )
                else:
                    status, body = "current", bodies[selection["feature_id"]]
            response = {
                "revision": state["revision"],
                "selection_status": status,
                "selected_body": body,
                "model": result["model"],
            }
            if selection and "surface_id" in selection:
                response["selected_surface"] = (
                    surface
                    or self._surface(
                        result["model"],
                        selection["feature_id"],
                        selection["surface_id"],
                    )
                    if status == "current"
                    else None
                )
            return response

    def _surface(self, model, feature, reference):
        if (
            not isinstance(feature, str)
            or not isinstance(reference, str)
            or not reference
        ):
            raise CadError(
                "missing_surface", "Select a surface from the saved solid inspection"
            )
        topology = self.store.evaluations.get(
            BINARY,
            {"topology_model": model, "feature_id": feature},
            lambda: topology_model(model, feature),
        )
        surface = topology["surfaces"].get(reference)
        if surface is None:
            raise CadError(
                "missing_surface",
                "Surface is absent; inspect and reselect without guessing a replacement",
            )
        return {
            "reference": reference,
            "naming": topology["naming"],
            "support": surface,
            "faces": [f["id"] for f in topology["faces"] if f["surface"] == reference],
            "source_feature": next(
                f for f in model["features"] if f["id"] == surface["owner_feature"]
            ),
        }


def dispatch_selection(store, command):
    try:
        return {"result": Selection(store).execute(command)}
    except CadError as exc:
        return {"error": exc.detail}
    except (OSError, ValueError, TypeError) as exc:
        return {
            "error": {
                "code": "selection_error",
                "entity": "selection",
                "message": str(exc),
            }
        }


def require_selection(store, state, expected):
    """Check a preview/commit precondition while the caller owns the document lock."""
    if (
        not isinstance(expected, dict)
        or set(expected) != {"feature_id", "surface_id"}
        or not isinstance(expected["feature_id"], str)
        or not expected["feature_id"]
        or not isinstance(expected["surface_id"], (str, type(None)))
        or expected["surface_id"] == ""
    ):
        raise CadError(
            "invalid_command",
            "selection_guard requires feature_id and surface_id (or null for body-only)",
        )
    selection = Selection(store)
    current = selection._read()
    if (
        current is None
        or current["revision"] != state["revision"]
        or current["document_hash"] != hashlib.sha256(encode(state)).hexdigest()
        or current["feature_id"] != expected["feature_id"]
        or current.get("surface_id") != expected["surface_id"]
    ):
        raise CadError(
            "selection_conflict",
            "Saved selection changed; inspect the current context and replan the edit",
        )
    model = store.inspect_model(state["model"])
    if not any(b["feature_id"] == expected["feature_id"] for b in model["bodies"]):
        raise CadError(
            "selection_conflict", "Selected body is no longer a terminal solid"
        )
    if expected["surface_id"] is not None:
        selection._surface(
            model["model"], expected["feature_id"], expected["surface_id"]
        )
