"""Read-only, revision-bound positive-volume overlap between planar bodies."""

import json
import subprocess
from engine_transport import run as engine_run
from store import BINARY, CadError, encode


def inspect_interference(model, left, right):
    request = encode(dict(model=model, left=left, right=right))
    if len(request) > 1_048_576:
        raise CadError("request_limit", "Interference request exceeds 1 MiB")
    try:
        process = engine_run(BINARY, "--interference", request)
        reply = json.loads(process.stdout)
    except FileNotFoundError as exc:
        raise CadError("engine_unavailable", "Build the model engine first") from exc
    except subprocess.TimeoutExpired as exc:
        raise CadError(
            "engine_timeout", "Interference check exceeded 20 seconds"
        ) from exc
    except ValueError as exc:
        raise CadError("engine_failure", "Invalid interference reply") from exc
    if "error" in reply:
        error = reply["error"]
        raise CadError(error["code"], error["message"], error["entity"])
    if process.returncode:
        raise CadError("engine_failure", "Interference process failed")
    return reply["result"]


def dispatch_interference(store, command):
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
                interference=state["model"],
                left=command["left"],
                right=command["right"],
            )
            value = store.evaluations.get(
                BINARY,
                request,
                lambda: inspect_interference(
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
                "entity": "interference",
                "message": str(exc),
            }
        }
