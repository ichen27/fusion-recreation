# Bounded, cancellable CPU previews

Browser modeling previews now run outside the viewer's request loop. One worker per viewer evaluates an immutable model snapshot and builds its display geometry. The queue admits four outstanding jobs including the active job; extra requests return `queue_full`. The saved document lock is released before the worker starts.

**Cancel calculation** preserves the current draft and saved model. Cancellation kills the isolated worker process group, including a running Rust evaluator/tessellator, and reaps the worker before freeing its slot. Each job has a 30-second total deadline; the worker also enforces its own deadline if the scheduling host disappears. Closing the viewer cancels outstanding jobs. The queue retains at most 32 completed-job records and 8 MiB of encoded results, in addition to bounded pending snapshots. Results exceeding the retained budget fail explicitly.

A completed preview remains tied to its starting revision. Another client can commit while it runs; attempting to save that older preview then rejects with `revision_conflict`. Jobs never commit or import documents. Existing CLI/MCP previews and native imports remain synchronous. The queue limit is per viewer process, not a machine-wide scheduler.

## Evidence

The actual browser sequence changes width to 40, cancels, retries a real calculation, and explicitly saves. Cancellation leaves native bytes unchanged and uploads zero GPU buffers. A separate move-dialog cancellation retains its 5 mm draft and re-enables Preview. Process tests verify that cancellation kills a real child process, queued work is bounded, timeout failures preserve the model, and edits can proceed while a snapshot is being evaluated.

To make cancellation reliably visible, the browser acceptance harness holds its **first job for up to ten seconds before launching the engine**. This is synthetic delay, not a heavy CAD workload. The held job was cancelled after 614 ms of total job lifetime; that number is not cancellation latency. During a separate held job, an actual browser model read returned in 4.2 ms. The subsequent real two-block preview, including process startup and display preparation, took about 74.9 ms. These are individual observations on the recorded platform, not performance guarantees.

Process isolation and 200 ms polling add overhead for small models. This change provides bounded work and cancellation; it does not claim faster geometry computation. Large-model scaling, persistent workers, feature-level incremental reuse and machine-wide scheduling remain open.

```sh
python3 tools/ai-cad/verify_preview_recording.py
node --test tools/ai-cad/test_preview_client.mjs
# Optional actual browser cancellation reproduction, using a disposable copy:
cp examples/ai-cad/preview-jobs/cancelled.cad.json /tmp/preview-demo.cad.json
python3 tools/ai-cad/serve_preview_acceptance.py \
  --store /tmp/preview-demo.cad.json --measurements /tmp/preview-demo-timing.json
```

The test harness refuses to overwrite its measurement output. Use a fresh path for repeated runs. The ordinary viewer has no synthetic delay.

## Artifacts

- `browser-recording.json`: actual job submission/poll/cancel/retry/commit requests and replies. Poll timing and UUIDs are observational; the verifier maps IDs and checks terminal results exactly.
- `cancelled.cad.json`, `committed.cad.json`: editable native checkpoints before/after the sole saved edit.
- `browser-measurements.json`: actual cancellation draft state, zero-upload counter and HTTP responsiveness sample.
- `worker-measurements.json`: synthetic hold lifetime and separate real worker timing.
- `calculating.png`, `cancelled.png`, `committed.png`, `editor-cancelled.png`: actual browser UI evidence.

All tests use disposable documents. The user's existing working document is untouched.
