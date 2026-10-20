"""Read-only, revision-bound original-engine shared surface topology."""

import json
import subprocess
from engine_transport import run as engine_run
from store import BINARY, CadError, encode


def topology_model(model, feature_id):
    request = encode({"model": model, "feature_id": feature_id})
    if len(request) > 1_048_576:
        raise CadError("request_limit", "Topology request exceeds 1 MiB")
    try:
        process = engine_run(BINARY, "--topology", request)
        reply = json.loads(process.stdout)
    except FileNotFoundError as exc:
        raise CadError("engine_unavailable", "Build the model engine first") from exc
    except subprocess.TimeoutExpired as exc:
        raise CadError("engine_timeout", "Topology exceeded 20 seconds") from exc
    except ValueError as exc:
        raise CadError("engine_failure", "Invalid topology reply") from exc
    if "error" in reply:
        error = reply["error"]
        raise CadError(error["code"], error["message"], error["entity"])
    if process.returncode:
        raise CadError("engine_failure", "Topology process failed")
    return reply["result"]


def dispatch_topology(store, command):
    try:
        if (
            not isinstance(command, dict)
            or set(command) != {"expected_revision", "feature_id"}
            or not isinstance(command["feature_id"], str)
        ):
            raise CadError("invalid_command", "Expected revision and feature_id")
        with store.locked():
            state = store.load()
            if (
                type(command["expected_revision"]) is not int
                or command["expected_revision"] != state["revision"]
            ):
                raise CadError(
                    "revision_conflict",
                    "Refresh before inspecting topology of this solid",
                )
            request = {
                "topology_model": state["model"],
                "feature_id": command["feature_id"],
            }
            topology = store.evaluations.get(
                BINARY,
                request,
                lambda: topology_model(state["model"], command["feature_id"]),
            )
            return {"result": {"revision": state["revision"], **topology}}
    except CadError as exc:
        return {"error": exc.detail}
    except (OSError, ValueError, TypeError) as exc:
        return {
            "error": {
                "code": "host_error",
                "entity": "topology",
                "message": str(exc),
            }
        }
