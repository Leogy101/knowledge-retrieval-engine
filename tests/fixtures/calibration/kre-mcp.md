# Optional assistant tools

`python -m kre.mcp` makes the independently installed KRE package available through MCP stdio. The existing assistant client starts a child process. There is no network listener, third package, background service or required GCB dependency. The standard-library implementation uses bounded newline-delimited JSON-RPC and supports protocol versions 2025-11-25, 2025-06-18, 2025-03-26 and 2024-11-05. See the [MCP transport specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).

After explicitly ingesting approved documents into an owned database, configure the client's absolute Python executable with fixed host settings, for example:

```text
python -I -m kre.mcp --db /absolute/path/kre.sqlite3 --principal shared-pilot --collection pilot-shared --destination approved_remote --max-bytes 8000
```

The default tool surface is `kre_retrieve` and `kre_validate`. Retrieval accepts a query, narrower budgets, optional freshness/history controls and exact required references. It returns the separate `kre-required/1` wrapper with the unchanged nested context/0.1 response. Revalidation accepts that nested context. It is a snapshot check, not an atomic guard on a later model request.

Database path, principal, collection grants, destination and maximum context budget belong to startup configuration. Model arguments cannot replace them or provide ingestion paths, approval flags or identity claims. There is no MCP ingestion, lifecycle-editing, egress-relabeling or arbitrary-file tool in this milestone. Use the explicit local-owner CLI for source management. There is no recursive discovery of private workspaces.

**Local tool execution does not imply a local model destination.** A remote-model assistant can receive local tool results. The initial OpenClaw pilot therefore uses `approved_remote` and a dedicated synthetic/share-approved collection; sources without the matching egress permission are denied. Do not grant that label to private material simply to make a query succeed. Generic MCP supplies no verified red/green/yellow/black principal or downstream model identity.

`--destination local_only` requires `--local-client`: an operator attestation that the selected client actually uses only a local provider. That is an external trust condition, not something KRE discovers from an untrusted tool call. All callers of one static binding share the stated principal/scope; it cannot provide private per-agent isolation.

Optional `--enable-task-tools` adds `kre_checkpoint` and `kre_resume`, and is accepted only with the local-only/local-client binding. The first OpenClaw pilot leaves these off. Cards remain bounded, extractive and reference-validated. Tool-supplied assertions are unverified, source-evidence text must be exact, and resume excludes revoked/stale/superseded/out-of-scope evidence and dependent prose. This does not erase previously exported conversation text.

The server is serial and starts no scheduler. Unexpected failures return generic errors without tracebacks or SQLite details; ordinary missing-evidence diagnostics retain the requested references for accountability. Protocol requests are bounded to 64 KiB and outputs to 2 MiB; actual contexts retain the much smaller host cap. Duplicate JSON keys, nonfinite values, malformed tool names and authority-expanding fields are rejected. Changing the client session, disabling a connector or restarting its host may terminate the child; source/task data remains in the operator's database.

macOS with Python 3.11/3.13/3.14 and FTS5 is the tested environment. Linux/Windows are not claimed verified. Installed-SDK compatibility is separate from live OpenClaw discovery. The readiness handoff provides exact existing-installation changes, rollback and approval scope; no live configuration is changed by this package or this documentation.
