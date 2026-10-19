"""Test-only viewer: fail one module request to exercise visible startup recovery."""

import argparse
from pathlib import Path
from store import Store
from viewer import handler
from viewer_server import ViewerServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True)
    parser.add_argument("--port", type=int, default=8779)
    args = parser.parse_args()
    if not Path(args.store).exists():
        parser.error("Use a disposable copy of an existing native fixture")
    base = handler(Store(args.store), args.port)

    class Interrupted(base):
        fail_once = True

        def get(self):
            if self.path == "/stock-model.mjs" and Interrupted.fail_once:
                Interrupted.fail_once = False
                return self.reply(503, b"", "text/javascript")
            return super().get()

    server = ViewerServer(("127.0.0.1", args.port), Interrupted)
    print(f"Test-only interrupted startup: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.RequestHandlerClass.preview_jobs.close()


if __name__ == "__main__":
    main()
