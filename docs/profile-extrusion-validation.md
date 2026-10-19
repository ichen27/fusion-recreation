# Profile extrusion validation — 2026-10-19

## Scope

The original Rust model engine now accepts a named convex XY polygon profile and a dependent positive-Z extrusion. This extends the editable command/MCP workflow beyond origin blocks and one corner cut. Geometry construction and validation use exact rational arithmetic on the CPU. The browser displays derived float triangles/lines through WebGL 2; no GPU geometry computation or new inference integration is included.

## Evidence

- 26 model/HTTP integration tests pass against the compiled Rust binary, including eight profile tests. Profile cases cover both windings, rational and negative coordinates, a nonzero 1e-30 mm width, maximum coordinates/height, a 32-vertex profile, two solids sharing one profile, and 40 seeded affine triangle/rectangle cases. Analytic area × height is compared with the reported volume and an independent signed tetrahedron sum over returned faces. Vertex positions, edge use orientation and Euler counts are checked.
- Invalid cases include bow ties, a star with same-direction local turns, concavity, repeated points, collinear corners, vertex limits, duplicate/invalid vertex IDs, missing/forward references, coordinate range and nonpositive/excessive height. Invalid coordinate edits and fixed-thickness edits leave the saved file unchanged.
- Profile → extrusion → width edit produces exact volumes 57000 → 68400 mm³. Preview does not save; stable feature definitions, reopen, undo and redo are verified. Three command inputs, replies and editable snapshots are versioned in [the example](../examples/ai-cad/profile-extrusion/README.md).
- Real MCP stdio negotiation accepts the new discriminated feature schemas, previews and commits all three stages, and returns a structured invalid-profile diagnostic. This transport check does not invoke inference.
- The earlier six-call live-client recording still replays with identical results and snapshots. Existing block/corner geometry output is preserved.
- Browser verification on a temporary local document: unextruded outline appears; a separate CLI extrusion becomes visible through polling; width 100 → 120 previews and saves; undo returns 100 and redo restores 120; moving the tip outside the convex outline returns `invalid_profile` while revision and solid volume remain unchanged. The browser reports no page errors. Screenshots were visually inspected. Physical GPU speed/precision is not benchmarked.
- All 104 existing Python geometry/document tests pass. Rust format/Clippy, Python lint/format and JavaScript syntax/format checks pass. CI also replays the profile artifact set on Linux.

## Reproduce

Follow [setup and validation](../tools/ai-cad/README.md). The new checks are included in normal test discovery and the AI CAD workflow:

```sh
python3 -m unittest discover -s tools/ai-cad -p 'test_profiles.py' -v
python3 tools/ai-cad/verify_profile_example.py
.venv/bin/python tools/ai-cad/verify_mcp.py
```

`verify_profile_example.py --write` regenerates the exact JSON replies/snapshots from their command inputs. Screenshots require the browser viewer. The earlier recorded conversation is unchanged.

## Limits and compatibility

These bounded cases do not establish general CAD robustness. There is no general sketch constraint solver, nonconvex profile, curved edge, hole, arbitrary extrusion direction, boolean between bodies, or persistent boundary face naming. Vertex IDs remain stable only for the supported coordinate edits; adding/removing vertices is not implemented. The fixed parameter mechanism does not imply symmetry or dimensional relationships.

Schema version 1 adds feature kinds and an optional nonempty `profiles` reply field. Old documents still replay unchanged; old binaries will reject documents with the new features. Update the Rust engine and MCP adapter together and restart connected clients. The existing user working document and client configuration are preserved. New exported examples are public-safe fixture data.

GitHub branch protection remains unavailable for this private repository on the current plan (HTTP 403). Current-revision checks and review are verified manually before merge; this is not enforced protection.
