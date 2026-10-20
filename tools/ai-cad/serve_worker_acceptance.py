"""Run the normal viewer and retain worker reuse statistics after it closes."""

import argparse
import hashlib
import json
from pathlib import Path
from engine_transport import WORKER
from store import Store
from viewer import handler
from viewer_server import ViewerServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8797)
    args = parser.parse_args()
    before = hashlib.sha256(args.store.read_bytes()).hexdigest()
    server = ViewerServer(
        ("127.0.0.1", args.port), handler(Store(args.store), args.port)
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.RequestHandlerClass.preview_jobs.close()
        after = hashlib.sha256(args.store.read_bytes()).hexdigest()
        args.report.write_text(
            json.dumps(
                dict(
                    worker_starts=WORKER.starts,
                    worker_requests=WORKER.requests,
                    native_sha256_before=before,
                    native_sha256_after=after,
                ),
                indent=2,
            )
            + "\n"
        )
        WORKER.close()


if __name__ == "__main__":
    main()
