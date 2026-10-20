"""Read-only additive mass properties for distinct terminal occurrences."""

import json
import subprocess
from engine_transport import run as engine_run
from store import BINARY, CadError, encode


def measure_mass_set(model, parts):
    request = encode(dict(model=model, parts=parts))
    if len(request) > 1_048_576:
        raise CadError("request_limit", "Mass selection request exceeds 1 MiB")
    try:
        process = engine_run(BINARY, "--mass-set", request)
        reply = json.loads(process.stdout)
    except FileNotFoundError as exc:
        raise CadError("engine_unavailable", "Build the model engine first") from exc
    except subprocess.TimeoutExpired as exc:
        raise CadError(
            "engine_timeout", "Mass selection check exceeded 20 seconds"
        ) from exc
    except ValueError as exc:
        raise CadError("engine_failure", "Invalid mass_set reply") from exc
    if "error" in reply:
        error = reply["error"]
        raise CadError(error["code"], error["message"], error["entity"])
    if process.returncode:
        raise CadError("engine_failure", "Mass selection process failed")
    return reply["result"]


def dispatch_mass_set(store, command):
    try:
        if (
            not isinstance(command, dict)
            or set(command) != {"expected_revision", "parts"}
            or not isinstance(command["parts"], list)
            or not 1 <= len(command["parts"]) <= 16
            or any(
                not isinstance(p, dict)
                or set(p) != {"feature_id", "density_kg_per_m3"}
                or not isinstance(p["feature_id"], str)
                or not isinstance(p["density_kg_per_m3"], str)
                for p in command["parts"]
            )
        ):
            raise CadError(
                "invalid_command",
                "Expected revision and 1..16 parts with feature_id and rational density_kg_per_m3",
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
                mass_set=state["model"],
                parts=command["parts"],
            )
            value = store.evaluations.get(
                BINARY,
                request,
                lambda: measure_mass_set(state["model"], command["parts"]),
            )
            return {"result": {"revision": state["revision"], **value}}
    except CadError as exc:
        return {"error": exc.detail}
    except (OSError, ValueError, TypeError) as exc:
        return {
            "error": {
                "code": "host_error",
                "entity": "mass_set",
                "message": str(exc),
            }
        }
