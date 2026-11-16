# Compatibility

KRE requires Python 3.11 or later and SQLite compiled with FTS5. Runtime dependencies
are limited to Python's standard library. The package does not require GCB, a
model provider, embeddings or a server.

| Surface | Supported scope / evidence |
|---|---|
| Local CLI and Python `Store` | SQLite storage, explicit text/Markdown ingestion, retrieval, lifecycle, citations, required references and task cards. |
| MCP stdio | Bounded protocol, retrieval/validation and optional local-only task tools; tested with real local subprocess fixtures. |
| Existing OpenClaw | Optional MCP integration; a prior scoped pilot is evidence for that installed path, not all versions or automatic per-agent authorization. |
| GCB interoperability | Context contract `0.1` with independent fixture copies. Neither package imports the other. |
| Model execution | Not a KRE feature. KRE makes no inference calls. |
| Native governed routing | Not provided or enabled by KRE. |

## Platforms

Safe filesystem ingestion requires POSIX descriptor-relative opens and symlink
protections. Unsupported file APIs fail explicitly; they are not replaced by an
unsafe path check. Do not infer Windows ingestion support from a `py3-none-any`
wheel filename.

The final candidate was verified on macOS 26.3.1 arm64 with Python 3.11.15,
3.13.1 and 3.14.6. Each environment passed 313 of 314 public regression methods
with the same documented optional-source replay skip, all 24 installed CLI/MCP
workflow checks and explicit uninstall. SQLite FTS5 was available in 3.53.4
(Python 3.11/3.14) and 3.45.3 (Python 3.13). See the
[verification report](VERIFICATION.md) for exact scope and timings.

Linux and additional Python versions may be in the CI matrix, but are verified
only when the required jobs actually execute successfully. Consult [GitHub Actions](https://github.com/Leogy101/knowledge-retrieval-engine/actions)
and the published release provenance for actual runner versions and conclusions. Windows file ingestion is
not currently supported. This candidate makes no unexecuted platform claims.

## Limits that belong to the host

A static MCP principal/collection binding is a shared trust domain, not verified
per-agent identity. The host controls model destination and tool permissions.
A snapshot-validation success is not an atomic guarantee about later dispatch.
Returned source documents remain untrusted data. See [MCP setup](MCP.md) and
[security/privacy](../SECURITY.md).

The local `kre-required/1` and `kre-task/1` formats do not extend the context `0.1`
wire contract. Unsupported fields continue to fail validation. Keep a normal
backup before a supported schema migration; foreign/incomplete/future schemas
are rejected instead of guessed.
