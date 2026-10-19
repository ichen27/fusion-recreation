"""Replay browser job cancellation/retry and explicit commit against native files."""

import json
from pathlib import Path
import tempfile
import threading
from urllib.parse import parse_qs, urlsplit
from preview_jobs import PreviewJobs
from store import ROOT, Store, CadError, dispatch
from test_preview_jobs import until

EXAMPLE = ROOT / "examples/ai-cad/preview-jobs"


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "model.json"
        initial = (EXAMPLE / "cancelled.cad.json").read_bytes()
        path.write_bytes(initial)
        store = Store(path)
        first = True
        entered = threading.Event()

        def runner(snapshot, cancel):
            nonlocal first
            if first:
                first = False
                entered.set()
                if not cancel.wait(3):
                    raise AssertionError("Expected recorded cancellation")
                raise CadError("preview_cancelled", "Cancelled")
            return jobs._process(snapshot, cancel)

        jobs = PreviewJobs(store, runner=runner)
        ids = {}
        try:
            for row in json.loads((EXAMPLE / "browser-recording.json").read_text())[
                "calls"
            ]:
                command = row["command"]
                if row["path"] == "/api/command":
                    assert dispatch(store, command) == row["reply"]
                    continue
                if command is not None:
                    if command["action"] == "preview":
                        actual = jobs.start(command)
                        ids[row["reply"]["result"]["job_id"]] = actual["job_id"]
                        if len(ids) == 1:
                            assert entered.wait(2)
                        assert actual["revision"] == row["reply"]["result"]["revision"]
                    else:
                        assert command["action"] == "cancel"
                        jobs.cancel(ids[command["job_id"]])
                else:
                    id = ids[parse_qs(urlsplit(row["path"]).query)["id"][0]]
                    expected = row["reply"]["result"]
                    if expected["status"] in ("cancelled", "succeeded", "failed"):
                        actual = until(
                            lambda: (
                                value
                                if (value := jobs.get(id))["status"]
                                in ("cancelled", "succeeded", "failed")
                                else None
                            )
                        )
                        assert {**actual, "job_id": expected["job_id"]} == expected
                    else:
                        assert expected["status"] in ("queued", "running", "cancelling")
                        jobs.get(
                            id
                        )  # Scheduling/poll timing is intentionally nondeterministic.
                assert path.read_bytes() == initial
            assert json.loads(path.read_text()) == json.loads(
                (EXAMPLE / "committed.cad.json").read_text()
            )
            assert jobs.pending == 0 and jobs.bytes <= jobs.result_limit
        finally:
            jobs.close()
        measurements = json.loads((EXAMPLE / "browser-measurements.json").read_text())
        assert measurements["cancelled-ui"]["uploads"] == 0
        assert measurements["cancelled-ui"]["widthDraft"] == "40"
        assert (
            measurements["nested-ui"]["editorOpen"]
            and not measurements["nested-ui"]["computeDialogOpen"]
        )
        assert measurements["nested-ui"]["offsetDraft"] == "5"
        assert not measurements["nested-ui"]["previewDisabled"]
        assert measurements["responsiveness"]["computeDialogOpen"]
    print(
        "PASS: actual browser cancellation, real preview retry, explicit commit, native files and retained UI drafts; timing is observational"
    )


if __name__ == "__main__":
    main()
