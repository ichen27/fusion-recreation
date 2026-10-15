# Live Codex → original Rust CAD engine

On 2026-10-15, a real Codex CLI conversation created and edited a CAD part using ChatGPT subscription sign-in and the project's MCP tools. This closes the earlier gap between deterministic fixtures and a live natural-language client.

The test used Codex CLI 0.159.2, the existing configured model `gpt-6-astra` with high reasoning effort, and the unchanged engine/host from source commit `b0199b11f1e2d55ae7a881f1a8480b9d76e766ba`. `codex login status` reported ChatGPT authentication. No API key, local model or AI-provider credential was passed to the CAD server.

## Observed conversation

**Turn 1:** “Create a 100 × 60 × 12 mm block. Cut the +X/+Y vertical corner with a 10 mm setback along each adjacent edge. Fix thickness and corner size. Inspect, preview, then commit.”

Codex called `cad_inspect`, `cad_preview`, then `cad_commit`. It created named dimensions, a block feature, a corner-cut feature, and fixed thickness/setback constraints. The saved result was revision 1 with exact volume **71,400 mm³**.

**Turn 2, resumed in the same conversation:** “Make that block 20 mm wider while preserving its depth, thickness, and corner-cut size. Update the existing model, preview the edit, then commit it.”

Codex again inspected, previewed and committed. Its only modeling operation was:

```json
{"op":"adjust_parameter","id":"width","delta_mm":"20"}
```

It explicitly preserved `depth`, `thickness`, and `corner_size`. The saved result was revision 2: **120 × 60 × 12 mm**, 10 mm setback, exact volume **85,800 mm³**. Feature IDs and fixed constraints were unchanged.

## Artifacts

| Artifact | Contents |
|---|---|
| [recording.json](recording.json) | Exact prompts, actual tool arguments, compact observed results, assistant messages, client/model provenance and reported token usage |
| [created.cad.json](created.cad.json) | Actual editable snapshot after the first live turn |
| [widened.cad.json](widened.cad.json) | Actual editable snapshot after the second live turn, including undo history and transaction receipts |
| [final.reply.json](final.reply.json) | Reopened final model with complete exact boundary geometry |
| [viewer.png](viewer.png) | Browser view of the actual live-generated result |

Copy a snapshot to a working directory before opening/editing it. The [main quickstart](../../../tools/ai-cad/README.md) explains the viewer and MCP connection.

## Reproduce the accepted edits without inference

Build the Rust engine, then run:

```sh
python3 tools/ai-cad/verify_codex_recording.py
```

This replays all six recorded calls against a fresh document, compares each observed result, reopens both snapshots, verifies width is the only changed parameter, checks exact volumes, and tests undo. It runs in CI without a subscription or provider credentials. It tests the accepted program, not future natural-language behavior.

For a fresh inference test, connect the MCP server to an empty document and send the two prompts from `recording.json` to a signed-in client. This uses the client's normal plan allowance. Do not repeat the create prompt against an existing part and assume it is a reset operation.

## Evidence boundaries

The live run used a per-invocation MCP configuration, isolated from unrelated user integrations. It used the existing ChatGPT login and model preference. Shell execution, multi-agent tools and app integrations were disabled for this CAD test; only the six recorded CAD tool calls executed. The second turn used `codex exec resume` with the first session ID.

Raw JSONL logs, stderr, local paths and conversation IDs remain in ignored local scratch. This export deliberately includes CAD tool arguments and relevant outputs rather than private runtime context or reasoning. SHA-256 hashes of the raw event files are recorded for local correlation; they are not independent attestation. The only client warning concerned the experimental `skip_host_skill_discovery` setting used for test isolation; it did not prevent completion.

This is one successful two-turn case, not a statistical reliability evaluation. Claude subscription authentication, desktop session hot-loading, unsupported geometry and broader modeling tasks remain untested here. API billing amounts are not inferred from token counters. Source and artifacts retain the repository's existing ownership/license status.
