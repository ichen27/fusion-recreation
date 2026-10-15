# Dependency attribution

The Rust modeling implementation is original project code. It uses these general
arithmetic/serialization dependencies; no third-party CAD kernel is linked.
Versions are resolved by `Cargo.lock`. License expressions below are copied from
the locked packages' Cargo metadata, not a new license grant by this project.
Dependencies are downloaded by Cargo and their source/license files are not
vendored here. Redistributing compiled binaries requires preserving applicable
notices and satisfying the selected dependency license terms.

| Packages | Upstream | Declared license |
|---|---|---|
| num-bigint 0.4.8, num-integer 0.1.47, num-rational 0.4.2, num-traits 0.2.19 | [rust-num](https://github.com/rust-num) | MIT OR Apache-2.0 |
| serde, serde_core, serde_derive 1.0.229 | [Serde](https://github.com/serde-rs/serde) | MIT OR Apache-2.0 |
| serde_json 1.0.154 | [Serde JSON](https://github.com/serde-rs/json) | MIT OR Apache-2.0 |
| autocfg 1.5.1 | [autocfg](https://github.com/cuviper/autocfg) | Apache-2.0 OR MIT |
| itoa 1.0.18 | [itoa](https://github.com/dtolnay/itoa) | MIT OR Apache-2.0 |
| memchr 2.8.3 | [memchr](https://github.com/BurntSushi/memchr) | Unlicense OR MIT |
| proc-macro2 1.0.107, quote 1.0.47, syn 3.0.9 | [dtolnay](https://github.com/dtolnay) | MIT OR Apache-2.0 |
| unicode-ident 1.0.27 | [unicode-ident](https://github.com/dtolnay/unicode-ident) | (MIT OR Apache-2.0) AND Unicode-3.0 |
| zmij 1.0.23 | [zmij](https://github.com/dtolnay/zmij) | MIT |

Optional validation uses [cadquery-ocp](https://github.com/CadQuery/OCP) 8.0.1.1.0
(OCP 8.0.1.1) and OCCT. Existing native dependency notices are in
[`../../deps/NOTICES.md`](../../deps/NOTICES.md). Optional plots use Matplotlib.
These are reference/illustration tools, not a hidden geometry fallback.
No Autodesk binary, decompiled implementation or user design is included.
