"""One local document, serialized writers, exact Rust evaluation, atomic snapshots.

The host owns persistence/history. Only Rust interprets modeling operations.
POSIX only (macOS/Linux); the lock file is permanent and never unlinked.
"""

import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from result_cache import ResultCache

ROOT = Path(__file__).resolve().parents[2]
BINARY = ROOT / "crates/model-engine/target/release/model-engine"
MAX_BYTES = 16 * 1024 * 1024
EMPTY = {"parameters": {}, "features": [], "fixed": {}}


class CadError(Exception):
    def __init__(self, code, message, entity="document"):
        super().__init__(message)
        self.detail = {"code": code, "message": message, "entity": entity}


def encode(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def evaluate(model, operations=None, preserve=None):
    request = {
        "schema_version": 1,
        "model": model,
        "operations": operations or [],
        "preserve": preserve or [],
    }
    data = encode(request)
    if len(data) > 1_048_576:
        raise CadError("request_limit", "Model request exceeds 1 MiB")
    try:
        process = subprocess.run(
            [str(BINARY)], input=data, capture_output=True, timeout=20
        )
    except FileNotFoundError as exc:
        raise CadError(
            "engine_unavailable", "Build crates/model-engine in release mode first"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise CadError(
            "engine_timeout", "Geometry evaluation exceeded 20 seconds"
        ) from exc
    try:
        reply = json.loads(process.stdout)
    except ValueError as exc:
        raise CadError(
            "engine_failure", "Geometry process returned no valid reply"
        ) from exc
    if "error" in reply:
        e = reply["error"]
        raise CadError(e["code"], e["message"], e["entity"])
    if process.returncode:
        raise CadError("engine_failure", "Geometry process failed")
    return reply["result"]


def fresh():
    return {
        "schema_version": 1,
        "revision": 0,
        "model": copy.deepcopy(EMPTY),
        "undo": [],
        "redo": [],
        "receipts": {},
    }


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.evaluations = ResultCache()

    def inspect_model(self, model):
        return self.evaluations.get(BINARY, model, lambda: evaluate(model))

    def load(self):
        if not self.path.exists():
            return fresh()
        try:
            with self.path.open("rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("document exceeds 16 MiB")
            envelope = json.loads(raw)
            state = envelope["state"]
            if hashlib.sha256(encode(state)).hexdigest() != envelope["sha256"]:
                raise ValueError("checksum mismatch")
            if set(state) != set(fresh()) or state["schema_version"] != 1:
                raise ValueError("unsupported document schema")
            if (
                type(state["revision"]) is not int
                or not 0 <= state["revision"] <= 9007199254740991
            ):
                raise ValueError("invalid revision")
            if not isinstance(state["undo"], list) or not isinstance(
                state["redo"], list
            ):
                raise ValueError("invalid history")
            if (
                len(state["undo"]) > 64
                or len(state["redo"]) > 64
                or len(state["receipts"]) > 1024
            ):
                raise ValueError("history/receipt limit exceeded")
            if not isinstance(state["receipts"], dict):
                raise ValueError("invalid receipts")
            for tx, receipt in state["receipts"].items():
                if (
                    not isinstance(tx, str)
                    or not isinstance(receipt, dict)
                    or set(receipt) != {"request", "revision"}
                ):
                    raise ValueError("invalid receipt")
                if (
                    not isinstance(receipt["request"], str)
                    or type(receipt["revision"]) is not int
                    or not 0 < receipt["revision"] <= state["revision"]
                ):
                    raise ValueError("invalid receipt fields")
            # History is executable data: check every snapshot before trusting it.
            for model in [state["model"], *state["undo"], *state["redo"]]:
                self.inspect_model(model)
            return state
        except (ValueError, KeyError, TypeError, CadError) as exc:
            raise CadError("invalid_document", str(exc)) from exc

    def save(self, state):
        data = encode(
            {"sha256": hashlib.sha256(encode(state)).hexdigest(), "state": state}
        )
        if len(data) > MAX_BYTES:
            raise CadError(
                "document_limit", "Document exceeds 16 MiB; save a new working document"
            )
        temporary = None
        published = False
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.path.parent, prefix=".cad-", delete=False
            ) as stream:
                temporary = stream.name
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            published = True
            fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            code = "commit_uncertain" if published else "save_failed"
            message = (
                "Snapshot was published but durability was not confirmed; inspect and retry the SAME transaction ID"
                if published
                else "Save failed before publication; original document is intact"
            )
            raise CadError(code, message) from exc
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def execute(self, command):
        with self.path.with_suffix(self.path.suffix + ".lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                return self._execute(command)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _execute(self, command):
        if not isinstance(command, dict):
            raise CadError("invalid_command", "Expected an object")
        action = command.get("action")
        fields = {"action"}
        if action in ("preview", "commit"):
            fields |= {"expected_revision", "operations", "preserve"}
        if action in ("commit", "undo", "redo"):
            fields |= {"expected_revision", "transaction_id"}
        if (
            action not in ("inspect", "preview", "commit", "undo", "redo")
            or set(command) != fields
        ):
            raise CadError(
                "invalid_command",
                "Wrong action or fields; consult the command contract",
            )
        if len(encode(command)) > 262144:
            raise CadError("request_limit", "Command exceeds 256 KiB")
        state = self.load()
        result = {
            "revision": state["revision"],
            "can_undo": bool(state["undo"]),
            "can_redo": bool(state["redo"]),
        }
        mutation = action in ("commit", "undo", "redo")
        if mutation:
            tx = command["transaction_id"]
            if not isinstance(tx, str) or not 1 <= len(tx) <= 128:
                raise CadError(
                    "invalid_transaction",
                    "Transaction ID must contain 1..128 characters",
                )
            digest = hashlib.sha256(encode(command)).hexdigest()
            if tx in state["receipts"]:
                receipt = state["receipts"][tx]
                if receipt["request"] != digest:
                    raise CadError(
                        "transaction_conflict",
                        "Transaction ID was already used for a different request",
                    )
                return {
                    **result,
                    "replayed": True,
                    "committed_revision": receipt["revision"],
                    **self.inspect_model(state["model"]),
                }
            if len(state["receipts"]) >= 1024:
                raise CadError(
                    "receipt_limit",
                    "1024 transactions reached; start a new working document",
                )
        if action != "inspect":
            if (
                type(command["expected_revision"]) is not int
                or command["expected_revision"] != state["revision"]
            ):
                raise CadError(
                    "revision_conflict",
                    f"Expected current revision {state['revision']}; inspect and replan",
                )
        if action in ("inspect", "preview", "commit"):
            if action != "inspect" and (
                not isinstance(command["operations"], list)
                or not isinstance(command["preserve"], list)
            ):
                raise CadError(
                    "invalid_command", "operations and preserve must be arrays"
                )
            evaluated = (
                self.inspect_model(state["model"])
                if action == "inspect"
                else evaluate(
                    state["model"], command.get("operations"), command.get("preserve")
                )
            )
            if not mutation:
                return {**result, "preview": action == "preview", **evaluated}
            if evaluated["model"] == state["model"]:
                raise CadError("no_change", "Commit would not change the model")
            state["undo"] = (state["undo"] + [state["model"]])[-64:]
            state["redo"] = []
            state["model"] = evaluated["model"]
        else:
            source, target = ("undo", "redo") if action == "undo" else ("redo", "undo")
            if not state[source]:
                raise CadError("empty_history", f"Nothing to {action}")
            state[target] = (state[target] + [state["model"]])[-64:]
            state["model"] = state[source].pop()
            evaluated = self.inspect_model(state["model"])
        state["revision"] += 1
        if state["revision"] > 9007199254740991:
            raise CadError("revision_limit", "Revision limit reached")
        state["receipts"][tx] = {"request": digest, "revision": state["revision"]}
        self.save(state)
        return {
            "revision": state["revision"],
            "committed_revision": state["revision"],
            "replayed": False,
            "can_undo": bool(state["undo"]),
            "can_redo": bool(state["redo"]),
            **evaluated,
        }


def dispatch(store, command):
    try:
        return {"result": store.execute(command)}
    except CadError as exc:
        return {"error": exc.detail}
    except (OSError, ValueError, TypeError) as exc:
        return {
            "error": {"code": "host_error", "entity": "document", "message": str(exc)}
        }
