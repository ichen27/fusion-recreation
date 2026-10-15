# Dependency attribution

Original model, host and viewer source is project code. Original source/artifacts have no selected public redistribution license; resolve that before a public release.

Rust uses the same arithmetic/serialization dependencies as the [boundary kernel notices](../../experiments/2026-10-15-rust-boundary/THIRD_PARTY.md); exact versions are in `crates/model-engine/Cargo.lock`. No CAD kernel dependency is added. The browser renderer uses the platform WebGL 2 API with no third-party renderer.

Optional MCP dependencies below are installed, not vendored. This metadata inventory is not a replacement for each distribution's license terms/files. Preserve applicable notices when distributing dependencies or binaries. Exact versions are pinned in `requirements.lock`.

| Distribution | Declared license metadata | Upstream metadata |
|---|---|---|
| annotated-types 0.8.0 | MIT | Homepage, https://github.com/annotated-types/annotated-types |
| anyio 4.15.1 | MIT | Documentation, https://anyio.readthedocs.io/en/latest/ |
| attrs 26.1.0 | MIT | Documentation, https://www.attrs.org/ |
| cffi 2.1.1 | MIT-0 | Documentation, https://cffi.readthedocs.io/ |
| click 8.5.0 | BSD-3-Clause | Changes, https://click.palletsprojects.com/page/changes/ |
| cryptography 50.0.2 | Apache-2.0 OR BSD-3-Clause | changelog, https://cryptography.io/en/latest/changelog/ |
| h11 0.16.0 | MIT | https://github.com/python-hyper/h11 |
| httpcore2 2.13.1 | BSD-3-Clause | Changelog, https://github.com/pydantic/httpx2/blob/main/src/httpcore2/CHANGELOG.md |
| httpx2 2.13.1 | BSD-3-Clause | Changelog, https://github.com/pydantic/httpx2/blob/main/src/httpx2/CHANGELOG.md |
| idna 3.20 | BSD-3-Clause | Changelog, https://github.com/kjd/idna/blob/master/HISTORY.md |
| jsonschema 4.26.0 | MIT | Homepage, https://github.com/python-jsonschema/jsonschema |
| jsonschema-specifications 2025.9.1 | MIT | Documentation, https://jsonschema-specifications.readthedocs.io/ |
| mcp 2.3.0 | MIT | Homepage, https://modelcontextprotocol.io |
| mcp-types 2.3.0 | MIT | Homepage, https://modelcontextprotocol.io |
| opentelemetry-api 1.45.1 | Apache-2.0 | Homepage, https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-api |
| pycparser 3.11 | BSD-3-Clause | Homepage, https://github.com/eliben/pycparser |
| pydantic 2.14.1 | MIT | Homepage, https://github.com/pydantic/pydantic |
| pydantic_core 2.50.1 | MIT | https://github.com/pydantic/pydantic |
| PyJWT 2.15.1 | MIT | Homepage, https://github.com/jpadilla/pyjwt |
| python-multipart 0.0.32 | Apache-2.0 | Homepage, https://github.com/Kludex/python-multipart |
| referencing 0.37.0 | MIT | Documentation, https://referencing.readthedocs.io/ |
| rpds-py 2026.9.1 | MIT | Documentation, https://rpds.readthedocs.io/ |
| sse-starlette 3.5.0 | BSD-3-Clause | Homepage, https://github.com/sysid/sse-starlette |
| starlette 1.8.0 | BSD-3-Clause | Homepage, https://github.com/Kludex/starlette |
| truststore 0.10.5 | MIT | Documentation, https://truststore.readthedocs.io |
| typing-inspection 0.4.4 | MIT | Homepage, https://github.com/pydantic/typing-inspection |
| typing_extensions 4.16.0 | PSF-2.0 | Bug Tracker, https://github.com/python/typing_extensions/issues |
| uvicorn 0.54.0 | BSD-3-Clause | Changelog, https://uvicorn.dev/release-notes |
