"""Verify retained baseline replies for CPU prefix reuse; no performance threshold."""

import hashlib
import json
from benchmark_rebuild import run
from store import BINARY, ROOT, encode


def verify(write=False):
    directory = ROOT / "examples/ai-cad/transaction-reuse"
    report = json.loads((directory / "comparison.json").read_text())
    assert len(report["rows"]) == 6
    for row in report["rows"]:
        name = row["name"]
        data = (directory / f"{name}.request.json").read_bytes()
        actual, _, _ = run(BINARY, data)
        assert (
            hashlib.sha256(encode(actual)).hexdigest() == row["exact_reply_sha256"]
        ), name
        path = directory / f"{name}.response.json"
        if write:
            path.write_text(json.dumps(actual, indent=2) + "\n")
        assert actual == json.loads(path.read_text()), name
    print(
        "PASS: six baseline-equivalent full replies, including cavity and 32-feature root/late edits"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    verify(parser.parse_args().write)
