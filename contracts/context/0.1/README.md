# Context contract 0.1

The schemas and synthetic fixtures here are byte-identical copies of the verified
G0/K0 subset. K2 preserves that exact subset. There is no companion-package,
third-package, database, server, or protocol-library runtime dependency.

Use Store.context(request) or `kre context --request request.json`. The local-owner
CLI binds the `local` scope reference; the copied fixture uses `demo-read`, which
requires an appropriately configured library caller. Trusted host scope grants
cannot be created or enlarged by request fields.

Insert only context_text into the model prompt. Items provide the same evidence
for inspection/validation. Byte accounting includes rendered citations and labels;
the outer transport has a separate 1 MiB ceiling. UTF-8 bytes are approximate
tokens, not a provider-token guarantee. The host counts its complete prompt and
checks egress restrictions before dispatch.

Supported: current/historical lexical retrieval, freshness/source filters, line
citations, bounded context and safe errors. Unsupported fields are rejected:
as-of queries, required evidence, task-resume transport, tokenizer negotiation,
remote destination sets, extensions and MCP. Coverage stays unknown: lexical rank
does not prove a sufficient answer.

K2 adds separate local `context_required` and task checkpoint/resume APIs. Their
wrappers are not 0.1 wire extensions: normal requests still reject required/task
fields. The nested context from `context_required` uses this unchanged schema.

Run `PYTHONPATH=src python3 -m unittest discover -s tests` from the repository root.
The separate milestone runner validates both schemas and real KRE output with a
development-only JSON Schema validator. It is not a package dependency. Local
pre-use validation checks generation/content but cannot retract already-delivered
context or atomically cancel an external provider send.
