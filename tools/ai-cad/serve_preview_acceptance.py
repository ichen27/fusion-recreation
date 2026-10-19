"""Test-only browser harness: hold the first preview before real engine launch.

Use a disposable copy of a native fixture. This hold makes cancellation visible;
it is not a geometry performance workload. Later jobs use the real worker.
"""

import argparse
from viewer_server import ViewerServer
import json
from pathlib import Path
import time
from store import CadError, Store
from viewer import handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True)
    parser.add_argument("--measurements", required=True)
    parser.add_argument("--port", type=int, default=8775)
    args = parser.parse_args()
    output = Path(args.measurements)
    if output.exists():
        parser.error("Measurement output already exists")
    server = ViewerServer(
        ("127.0.0.1", args.port), handler(Store(args.store), args.port)
    )
    jobs = server.RequestHandlerClass.preview_jobs
    first, rows = True, []

    def runner(snapshot, cancel):
        nonlocal first
        started = time.monotonic()
        if first:
            first = False
            if cancel.wait(10):
                rows.append(
                    {
                        "fixture": "ten-second synthetic hold before engine launch",
                        "outcome": "cancelled",
                        "elapsed_ms": (time.monotonic() - started) * 1000,
                    }
                )
                raise CadError("preview_cancelled", "Cancelled test hold")
        result = jobs._process(snapshot, cancel)
        rows.append(
            {
                "fixture": "real geometry and display subprocess",
                "outcome": "completed",
                "elapsed_ms": (time.monotonic() - started) * 1000,
            }
        )
        return result

    jobs.runner = runner
    print(f"Test-only preview viewer: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        jobs.close()
        output.write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
