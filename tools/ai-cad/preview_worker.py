"""One disposable preview process; no document path or persistence capability."""

import json
import signal
import sys
from exports import display
from store import CadError, encode, evaluate


class PreviewExpired(BaseException):
    """Escape display fallback handlers so the whole job has one deadline."""


def main(timeout=30):
    def expired(signum, frame):
        raise PreviewExpired()

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        raw = sys.stdin.buffer.read(1_048_577)
        if len(raw) > 1_048_576:
            raise CadError("request_limit", "Preview snapshot exceeds 1 MiB")
        request = json.loads(raw)
        result = evaluate(request["model"], request["operations"], request["preserve"])
        reply = display({"result": {**request["metadata"], "preview": True, **result}})
    except PreviewExpired:
        reply = {
            "error": {
                "code": "preview_timeout",
                "entity": "preview",
                "message": "Preview exceeded its total time budget",
            }
        }
    except CadError as exc:
        reply = {"error": exc.detail}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        reply = {
            "error": {
                "code": "preview_failed",
                "entity": "preview",
                "message": str(exc),
            }
        }
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    sys.stdout.buffer.write(encode(reply))


if __name__ == "__main__":
    main()
