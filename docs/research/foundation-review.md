# Foundation review, 2026-10-12

A fresh reviewer inspected the native foundation and reproduced three findings:

1. Document-only save could discard persisted command history.
2. Disconnect during a large worker diagnostic could block parent and child.
3. Profile validation depended on absolute world position.

Regression tests were observed failing before fixes. The implementation now preserves unchanged command-managed state and rejects document-only mutations, closes the result pipe before waiting for a disconnected worker, and computes profile predicates using local extents and area with distinct linear/area tolerances.

The reviewer independently reran kernel, storage, commands, recovery and runner checks (5/5 passed) and found no remaining high/medium issue in these fixes. This review does not certify deferred capabilities or exhaustive numerical robustness.

A subsequent publication-boundary review found that retrying an uncertain commit
must confirm durability before reporting success. The first test reproduced
ordinary success without confirmation; the fix syncs the current manifest
directory under the writer lock. The regression covers uncertain publication,
failed retry confirmation, then successful replay without duplicate mutation.
The reviewer independently reran commands, storage, recovery and runner (4/4
passed) and confirmed the targeted fix at 5f779e3.
