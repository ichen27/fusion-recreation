# Reused native process with bounded requests

The document host now reuses one serial Rust process for evaluation, tessellation, dependency explanation, measurement and topology. Each call still evaluates its own complete request. The existing request-local prefix reuse and host result caches retain their separate behavior; the worker holds no cross-request geometry model.

The single-request CLI remains available. The host uses `model-engine --worker`, with a mode byte and bounded length-prefixed UTF-8 JSON. Requests are limited to1MiB and replies to16MiB. A20-second host deadline includes waiting for the worker lock and pipe I/O. Timeout, transport failure or binary replacement closes the process; a later call starts another. A failed call is never automatically retried. Native geometry errors leave the worker available for the next request. The host still owns atomic document writes and history.

## Measured evidence

`benchmark.json` retains15 samples per workload, alternating order, on the recorded Darwin/arm64 environment. Ten workloads and160 worker calls used one process, with exact replies equal to fresh CLI processes. Selected medians:

| Workload | Fresh process | Reused worker |
|---|---:|---:|
| Cavity inspection |22.93ms|20.03ms|
| Cavity dimension edit |43.36ms|40.11ms|
| Last placement among32 linked features |22.51ms|19.69ms|
| Counter-sink display mesh |4.45ms|2.13ms|
| Loft explanation |3.15ms|0.93ms|
| Loft measurement |3.44ms|1.12ms|
| Loft shared topology |3.29ms|1.03ms|

These are warm-worker wall latencies, including host framing/JSON validation. They show process-start savings on this machine. They do not establish parallel geometry throughput, GPU acceleration, cross-request geometry reuse or large-document performance. Timings are not CI pass/fail thresholds.

## Retained artifacts

- Ten `*.request.json` inputs and`benchmark.json`: editable workloads, raw timings, environment/binary identity and reply hashes. Replies are regenerated and compared exactly during reproduction.
- `browser-recording.json`: four actual browser calls—selection, explanation, measurement and topology—against the [saved loft](../planar-loft/browser-deeper.cad.json).
- `browser-runtime.json`: eight native calls used one process during native-history loading and those reads; the before/after native SHA-256 is unchanged.

Tests compare all five native modes against the single-request CLI and cover concurrent distinct calls, geometry errors followed by valid calls, lock/pipe deadlines, EOF, malformed/oversized replies, oversized/truncated input, killed-worker recovery, binary replacement and fork isolation. Existing preview cancellation and transaction suites run with the new transport. CLI/MCP and browser recording replays retain their prior replies.

## Reproduce

Build the current engine using the [workflow setup](../../../tools/ai-cad/README.md). Then:

```sh
python -m unittest discover -s tools/ai-cad -p test_engine_transport.py -v
python tools/ai-cad/verify_native_worker.py
python tools/ai-cad/benchmark_native_worker.py --samples 15
```

The host remains POSIX-only. One worker belongs to each host process; separate preview jobs have their own process lifetime and remain cancellable as a process group. Rebuild the native binary when updating host code. Parent and forked children never share native pipes. Worker stderr is discarded; structured native errors and bounded transport diagnostics remain the public error path.
