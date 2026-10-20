"""Revision-bound mass measurement using validated persistent material assignments."""

from mass_properties import measure_mass_set
from store import BINARY, CadError


def dispatch_material_mass(store, command):
    try:
        if (
            not isinstance(command, dict)
            or set(command) != {"expected_revision", "feature_ids"}
            or not isinstance(command["feature_ids"], list)
            or not 1 <= len(command["feature_ids"]) <= 16
            or any(not isinstance(i, str) for i in command["feature_ids"])
        ):
            raise CadError(
                "invalid_command",
                "Expected revision and1..16 distinct solid feature_ids",
            )
        ids = sorted(command["feature_ids"])
        if len(set(ids)) != len(ids):
            raise CadError("invalid_command", "Select each solid once")
        with store.locked():
            state = store.load()
            if (
                type(command["expected_revision"]) is not int
                or command["expected_revision"] != state["revision"]
            ):
                raise CadError(
                    "revision_conflict", "Refresh before measuring assigned materials"
                )
            evaluated = store.inspect_model(state["model"])
            bodies = {b["feature_id"] for b in evaluated["bodies"]}
            assigned = evaluated.get("resolved_materials", {})
            sources, parts = {}, []
            for feature in ids:
                if feature not in bodies:
                    raise CadError(
                        "missing_body", "Select a saved terminal solid", feature
                    )
                resolved = assigned.get(feature, {"status": "unassigned"})
                if resolved["status"] != "assigned":
                    raise CadError(
                        "material_conflict"
                        if resolved["status"] == "conflict"
                        else "unassigned_material",
                        "Assign an explicit uniform material before measuring this solid",
                        feature,
                    )
                sources[feature] = resolved
                parts.append(
                    dict(
                        feature_id=feature,
                        density_kg_per_m3=resolved["material"]["density_kg_per_m3"],
                    )
                )
            request = dict(material_mass=state["model"], parts=parts)
            result = store.evaluations.get(
                BINARY, request, lambda: measure_mass_set(state["model"], parts)
            )
            return {
                "result": {
                    "revision": state["revision"],
                    "material_sources": sources,
                    "density_policy": "persistent_uniform_feature_materials",
                    **result,
                }
            }
    except CadError as exc:
        return {"error": exc.detail}
    except (OSError, ValueError, TypeError) as exc:
        return {"error": dict(code="host_error", entity="materials", message=str(exc))}
