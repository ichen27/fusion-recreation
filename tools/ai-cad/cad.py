#!/usr/bin/env python3
"""Single-command JSON CLI. The document path is selected by the human host."""

import argparse
import json
import sys
from store import Store, dispatch

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True)
    args = parser.parse_args()
    try:
        data = sys.stdin.buffer.read(262145)
        if len(data) > 262144:
            raise ValueError("Command exceeds 256 KiB")
        reply = dispatch(Store(args.store), json.loads(data))
    except (ValueError, OSError) as exc:
        reply = {
            "error": {
                "code": "invalid_request",
                "entity": "request",
                "message": str(exc),
            }
        }
    print(json.dumps(reply))
    sys.exit(1 if "error" in reply else 0)
