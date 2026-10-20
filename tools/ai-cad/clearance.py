"""Read-only, revision-bound minimum material separation between planar bodies."""

import json
import subprocess
from engine_transport import run as engine_run
from store import BINARY, CadError, encode


def inspect_clearance(model, left, right):
    request = encode(dict(model=model, left=left, right=right))
    if len(request) > 1_048_576:
        raise CadError("request_limit", "Clearance request exceeds 1 MiB")
    try:
        process = engine_run(BINARY, "--clearance", request)
        reply = json.loads(process.stdout)
    except FileNotFoundError as exc:
        raise CadError("engine_unavailable", "Build the model engine first") from exc
    except subprocess.TimeoutExpired as exc:
        raise CadError("engine_timeout", "Clearance check exceeded 20 seconds") from exc
    except ValueError as exc:
        raise CadError("engine_failure", "Invalid clearance reply") from exc
    if "error" in reply:
        error = reply["error"]
        raise CadError(error["code"], error["message"], error["entity"])
    if process.returncode:
        raise CadError("engine_failure", "Clearance process failed")
    return reply["result"]


def dispatch_clearance(store, command):
    try:
        if (
            not isinstance(command, dict)
            or set(command) != {"expected_revision", "left", "right"}
            or not isinstance(command["left"], str)
            or not isinstance(command["right"], str)
        ):
            raise CadError(
                "invalid_command", "Expected revision and two terminal body IDs"
            )
        with store.locked():
            state = store.load()
            if (
                type(command["expected_revision"]) is not int
                or command["expected_revision"] != state["revision"]
            ):
                raise CadError(
                    "revision_conflict", "Refresh before checking these bodies"
                )
            request = dict(
                clearance=state["model"],
                left=command["left"],
                right=command["right"],
            )
            value = store.evaluations.get(
                BINARY,
                request,
                lambda: inspect_clearance(
                    state["model"], command["left"], command["right"]
                ),
            )
            return {"result": {"revision": state["revision"], **value}}
    except CadError as exc:
        return {"error": exc.detail}
    except (OSError, ValueError, TypeError) as exc:
        return {
            "error": {
                "code": "host_error",
                "entity": "clearance",
                "message": str(exc),
            }
        }
