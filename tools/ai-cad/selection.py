"""Revision-bound workspace selection shared by the browser and MCP process.

Selection is a disposable sidecar, never part of native model history/exports.
The document lock serializes selection with model edits across processes.
"""

import hashlib
import json
import os
import tempfile
from store import CadError, encode


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
                != {"schema_version", "revision", "document_hash", "feature_id"}
                or type(value["schema_version"]) is not int
                or value["schema_version"] != 1
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
        ):
            raise CadError(
                "invalid_command", "Expected context or revision-bound select"
            )
        with self.store.locked():
            state = self.store.load()
            fingerprint = hashlib.sha256(encode(state)).hexdigest()
            result = self.store.inspect_model(state["model"])
            bodies = {b["feature_id"]: b for b in result["bodies"]}
            if action == "select":
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
            return {
                "revision": state["revision"],
                "selection_status": status,
                "selected_body": body,
                "model": result["model"],
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
