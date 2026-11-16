# Optional MCP and OpenClaw integration

KRE's supported assistant interface is bounded MCP over stdio. An existing client
starts `python -m kre.mcp` as a child process. KRE opens no network listener,
starts no scheduler and requires no GCB installation. Installing the Python
package does not install a plugin into OpenClaw or alter a Gateway.

## Operator-owned binding

Initialize an owned database and ingest approved documents with the local CLI.
Configure the existing client's command using the **absolute path to the Python
executable where KRE is installed**, fixed arguments and an explicit destination.
The exact client configuration location depends on its supported MCP interface;
this document is an argument recipe, not a universal OpenClaw configuration patch.

For a verified local-only client:

```text
python -I -m kre.mcp --db /absolute/path/knowledge.sqlite3 --principal project-reader --collection default --destination local_only --local-client --max-bytes 8000
```

Replace the example executable and database paths. `--local-client` is an operator
attestation that this client actually uses a local model; KRE cannot establish
that fact from a tool invocation. Do not use it for a remote-model assistant.

For an assistant whose model runs remotely:

```text
python -I -m kre.mcp --db /absolute/path/shared.sqlite3 --principal shared-reader --collection share-approved --destination approved_remote --max-bytes 8000
```

Only explicitly share-approved evidence may be sent. New sources default to
`local_only`; trusted operators can apply `kre update-policy SOURCE_ID --egress
approved_remote` after reviewing disclosure. Do not change that label merely to
make a denied query succeed. Use a dedicated collection/database for shared data.

Database, principal, collection grants, destination and maximum budget are host
settings. A tool call cannot change them. Generic MCP does not authenticate an
individual agent or the downstream model. Every caller of one static binding
shares the same trust domain; use separate bindings/databases where isolation is
needed.

## Default tools

| Tool | Purpose |
|---|---|
| `kre_retrieve` | Query fixed-scope evidence with narrower budgets and optional exact required references. |
| `kre_validate` | Revalidate the returned nested context before use. |

Retrieval returns a `kre-required/1` wrapper containing an unchanged context `0.1`
envelope. Validation accepts that nested `context`. The response carries one MCP
text-content representation, without an additional `structuredContent` copy.
Inside it, `items` and `context_text` represent the same evidence for different
consumers. A host that builds a prompt directly should inject `context_text` once;
actual MCP host message construction and provider token usage depend on the host.
No token savings are assumed from serialization size.

There is no default ingestion, lifecycle-editing, egress-relabeling or arbitrary
file tool. Use the local-owner CLI for those operations. Optional
`--enable-task-tools` adds `kre_checkpoint` and `kre_resume` only to an attested
local-only binding. It does not add generation or broader filesystem access.

Source text is untrusted evidence. Tool descriptions and result labels do not
replace a host's approval policy or downstream egress enforcement. Snapshot
validation detects changes/tampering but is not atomic with an external send.

## Verify without an assistant or inference

After installing the package, run:

```sh
python -I scripts/verify_user_workflow.py
```

The test starts the real stdio server against temporary synthetic knowledge,
negotiates the protocol, lists only the two default tools, retrieves and validates
a context, rejects an attempted scope expansion and closes the process. It does
not contact OpenClaw, start another installation, call a model or change live
configuration. This establishes the local protocol boundary, not universal host
compatibility.

The implementation supports protocol versions `2025-11-25`, `2025-06-18`,
`2025-03-26` and `2024-11-05`. Requests are newline-delimited JSON-RPC, serial,
bounded to 64 KiB; responses are capped at 2 MiB and retrieval context at the
smaller operator ceiling. Duplicate keys, malformed parameters and authority
expansion are rejected. No asynchronous task or cancellation feature is advertised.

## Existing OpenClaw setup and removal

Use the installed OpenClaw version's documented MCP registration interface, with
the fixed command above. Verify tool discovery and a synthetic retrieval before
granting a real collection. A previous scoped OpenClaw pilot demonstrated a
specific installation; it does not establish compatibility with every version or
per-agent identity. No private operator helper is required by KRE itself.

Disable or remove the KRE binding through the same client interface. Closing its
stdio child stops KRE; the database remains intact. If a particular host requires
a restart or wider permission change, that is a separate operator decision—not
an installation action performed by this package.
