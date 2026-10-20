"""Read-only, revision-bound original-engine exact engineering measurements."""

import json
import subprocess
from engine_transport import run as engine_run
from store import BINARY, CadError, encode


def measure_model(model, feature_id, density_kg_per_m3=None):
    payload = {"model": model, "feature_id": feature_id}
    if density_kg_per_m3 is not None:
        payload["density_kg_per_m3"] = density_kg_per_m3
    request = encode(payload)
    if len(request) > 1_048_576:
        raise CadError("request_limit", "Measurement request exceeds 1 MiB")
    try:
        process = engine_run(BINARY, "--measure", request)
        reply = json.loads(process.stdout)
    except FileNotFoundError as exc:
        raise CadError("engine_unavailable", "Build the model engine first") from exc
    except subprocess.TimeoutExpired as exc:
        raise CadError("engine_timeout", "Measurement exceeded 20 seconds") from exc
    except ValueError as exc:
        raise CadError("engine_failure", "Invalid measurement reply") from exc
    if "error" in reply:
        error = reply["error"]
        raise CadError(error["code"], error["message"], error["entity"])
    if process.returncode:
        raise CadError("engine_failure", "Measurement process failed")
    return reply["result"]


def dispatch_measure(store, command):
    try:
        if (
            not isinstance(command, dict)
            or not {"expected_revision", "feature_id"}.issubset(command)
            or not set(command).issubset(
                {"expected_revision", "feature_id", "density_kg_per_m3"}
            )
            or not isinstance(command["feature_id"], str)
            or (
                command.get("density_kg_per_m3") is not None
                and not isinstance(command["density_kg_per_m3"], str)
            )
        ):
            raise CadError(
                "invalid_command",
                "Expected revision, feature_id and optional rational density_kg_per_m3",
            )
        with store.locked():
            state = store.load()
            if (
                type(command["expected_revision"]) is not int
                or command["expected_revision"] != state["revision"]
            ):
                raise CadError(
                    "revision_conflict", "Refresh before measuring this solid"
                )
            request = {
                "measurement_model": state["model"],
                "feature_id": command["feature_id"],
            }
            density = command.get("density_kg_per_m3")
            if density is not None:
                request["density_kg_per_m3"] = density
            measurement = store.evaluations.get(
                BINARY,
                request,
                lambda: measure_model(state["model"], command["feature_id"], density),
            )
            return {"result": {"revision": state["revision"], **measurement}}
    except CadError as exc:
        return {"error": exc.detail}
    except (OSError, ValueError, TypeError) as exc:
        return {
            "error": {
                "code": "host_error",
                "entity": "measurement",
                "message": str(exc),
            }
        }
