# Optional assistant tools

`python -m gcb.mcp` exposes this package through newline-delimited MCP stdio. The existing client starts a child process; no network listener, scheduler, third package or mandatory service is installed. The transport uses only Python's standard library. Protocol versions 2025-11-25, 2025-06-18, 2025-03-26 and 2024-11-05 are supported. See the [MCP stdio specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).

Initialize an owned inventory with the ordinary CLI, then configure the client's command to the absolute Python executable in GCB's independent environment:

```text
python -I -m gcb.mcp --db /absolute/path/gcb.sqlite3 --model qwen3.5:9b
```

The endpoint defaults to `http://127.0.0.1:11434`; context/output request caps default to 4096/512. Flags `--endpoint`, `--context-tokens`, `--output-cap` and repeated `--model` are trusted operator configuration. Model IDs match exact native tags for this adapter. Keep the same caps used to research an existing deployment; conflicting facts do not silently overwrite immutable research. No metadata request or inference occurs merely from starting the tool server.

By default, only `gcb_models`, `gcb_status`, `gcb_bio`, `gcb_evidence` and `gcb_recommend` exist. Recommendations stay local, within the model allowlist, and `preview_only`. A selected eligible configuration with no positive observed task evidence is explicitly labeled `task_fit: not_demonstrated`. Samples are too small for broad competence claims.

An operator may add `--allow-profiling` to delegate bounded unpaid local profiling. That exposes `gcb_research`, `gcb_plan`, `gcb_start` and `gcb_cancel`. Normal chat flow is research → choose a documented configuration → plan → start → inspect status/bio → start again if pending. An already completed cell is not repeated. Tool arguments cannot change endpoints, database paths, model allowlists, caps, grants or routing policy. The startup delegation avoids repeated per-cell operator prompts; the host's ordinary tool approval policy still applies.

Plans have at most 16 attempts, 45 seconds per inference and 300 seconds accumulated execution time. A `gcb_start` call processes one cell, and a recovery cell can contain **two** attempts. Use a client tool timeout of at least 120 seconds when profiling is enabled, with parallel tool calls disabled. Read-only calls can use 60 seconds. Broader preexisting plans cannot borrow the tool server's narrower delegation. Status/evidence remain readable for allowed models.

The server is serial and does not advertise asynchronous task execution or background jobs. Cancellation notifications do not forcibly cancel an active provider call; between calls, `gcb_cancel` persists cancellation. Closing a client can terminate its child. Unknown completion remains unknown and is not automatically replayed; Ollama's work after a disconnected socket is not certified cancelled. Completed observations survive process changes.

This is a trusted local process boundary, not arbitrary-code sandboxing. MCP tool names and schemas are not execution authority. Inputs are bounded to 64 KiB, duplicate JSON keys/nonfinite numbers are rejected, errors omit raw arguments/provider bodies, and stdout contains only protocol frames. Windows profiling is disabled; macOS is tested and Linux remains unverified. The product does not inspect OpenClaw credentials or change agent assignments.

The readiness handoff's existing-OpenClaw plan uses the installed 2026.11.1 MCP client, globally disabled server entries and a single operator-selected pilot conversation. It requires separate approval before any live configuration change. A successful offline SDK connection does not prove discovery in every live agent runtime or complete native governance.
