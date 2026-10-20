"""Revision-bound terminal-solid inventory; identities are never inferred from shape."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from store import CadError, Store, encode

COLUMNS = (
    "revision",
    "source_model_sha256",
    "feature_id",
    "feature_kind",
    "quantity",
    "linked_source",
    "volume_mm3",
    "material_status",
    "material_name",
    "density_kg_per_m3",
    "material_source_features",
)


def csv_cell(value):
    text = str(value)
    # User-authored names may begin with spreadsheet formulas. Keep their literal
    # spelling in JSON; prefix risky CSV cells to prevent formula interpretation.
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def inventory_csv(result):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for row in result["rows"]:
        material = row["material"]
        assigned = material.get("material", {})
        values = (
            result["revision"],
            result["source_model_sha256"],
            row["feature_id"],
            row["feature_kind"],
            row["quantity"],
            row["linked_source"] or "",
            row["volume_mm3"],
            material["status"],
            assigned.get("name", ""),
            assigned.get("density_kg_per_m3", ""),
            json.dumps(material.get("source_features", []), ensure_ascii=False),
        )
        writer.writerow([csv_cell(value) for value in values])
    return buffer.getvalue()


def dispatch_inventory(store, command):
    try:
        if not isinstance(command, dict) or set(command) != {"expected_revision"}:
            raise CadError("invalid_command", "Expected only expected_revision")
        with store.locked():
            state = store.load()
            if (
                type(command["expected_revision"]) is not int
                or command["expected_revision"] != state["revision"]
            ):
                raise CadError(
                    "revision_conflict", "Refresh before reading the inventory"
                )
            evaluated = store.inspect_model(state["model"])
            features = {f["id"]: f for f in state["model"]["features"]}
            materials = evaluated.get("resolved_materials", {})
            rows = []
            for body in sorted(evaluated["bodies"], key=lambda b: b["feature_id"]):
                feature = features[body["feature_id"]]
                rows.append(
                    dict(
                        feature_id=feature["id"],
                        feature_kind=feature["kind"],
                        quantity=1,
                        linked_source=feature["source"]
                        if feature["kind"] == "instance"
                        else None,
                        volume_mm3=body["volume_mm3"],
                        material=materials.get(
                            feature["id"], dict(status="unassigned", source_features=[])
                        ),
                    )
                )
            result = dict(
                revision=state["revision"],
                source_model_sha256=hashlib.sha256(encode(state["model"])).hexdigest(),
                units="mm",
                density_units="kg/m^3",
                row_policy="one_per_terminal_solid",
                quantity_policy="one_body_not_connected_components",
                grouping_policy="none_no_part_equivalence_inferred",
                overlap_policy="each_terminal_solid_listed_separately",
                solid_count=len(rows),
                rows=rows,
                material_counts={
                    status: sum(r["material"]["status"] == status for r in rows)
                    for status in ("assigned", "unassigned", "conflict")
                },
            )
            result["csv"] = inventory_csv(result)
            return {"result": result}
    except CadError as exc:
        return {"error": exc.detail}
    except (OSError, ValueError, TypeError) as exc:
        return {"error": dict(code="host_error", entity="inventory", message=str(exc))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--revision", required=True, type=int)
    parser.add_argument("--format", choices=("json", "csv"), default="json")
    args = parser.parse_args()
    reply = dispatch_inventory(Store(args.store), dict(expected_revision=args.revision))
    if "error" in reply:
        print(json.dumps(reply))
        raise SystemExit(1)
    print(
        reply["result"]["csv"] if args.format == "csv" else json.dumps(reply, indent=2),
        end="" if args.format == "csv" else "\n",
    )
