# Foundation review, 2026-10-12

A fresh reviewer inspected the native foundation and reproduced three findings:

1. Document-only save could discard persisted command history.
2. Disconnect during a large worker diagnostic could block parent and child.
3. Profile validation depended on absolute world position.

Regression tests were observed failing before fixes. The implementation now preserves unchanged command-managed state and rejects document-only mutations, closes the result pipe before waiting for a disconnected worker, and computes profile predicates using local extents and area with distinct linear/area tolerances.

The reviewer independently reran kernel, storage, commands, recovery and runner checks (5/5 passed) and found no remaining high/medium issue in these fixes. This review does not certify deferred capabilities or exhaustive numerical robustness.
