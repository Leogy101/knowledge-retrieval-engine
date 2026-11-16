# Local workflow

KRE is a local-owner CLI and Python library. It does not create an AI agent or
call a model. Use separate databases for separate trust domains.

## Initialize, ingest and inspect

In a fresh working directory with KRE installed:

```sh
kre init
mkdir -p example-docs
printf '# Release\n\nRollback restores the amber snapshot after operator approval.\n' > example-docs/runbook.md
kre ingest example-docs/runbook.md --root example-docs --source-id runbook
kre search "rollback approval"
kre context "rollback approval" --budget 4000 --max-bytes 4000 > context.json
```

The default database is `.kre/knowledge.sqlite3`. Place `--db PATH` **before** the
command to choose another store. Ingestion prints `source_id` and `revision_id`.
Use `kre inspect REVISION_ID` to inspect the immutable stored source.

Each context item carries an exact source ID, revision, chunk, original line
range, returned-text SHA-256 and citation ID. Text normalization removes a leading
UTF-8 BOM and converts CRLF/CR to LF; it does not rewrite prose or trim source
lines. Inspect and cite the returned passage as written.

UTF-8 text/Markdown files must be at most 2 MiB, 100,000 lines and 10,000 chunks,
with at most 8,192 bytes per source line. A CLI ingestion batch accepts up to 100
explicit files. There is no PDF/Office/HTML extraction, OCR or recursive discovery.
A named root alias is allowed, but symlink descendants are rejected, including
links back into that root. Root ancestors, application code and database access
remain trusted; this is not an operating-system sandbox.

## Required evidence and a task checkpoint

For a task that depends on a known excerpt, record that precise reference. This
example uses the context above and does not guess which other facts are needed:

```sh
python - <<'PY'
import json
from pathlib import Path
item = json.loads(Path('context.json').read_text())['items'][0]
ref = {key: item[key] for key in
       ('source_id', 'revision_id', 'chunk_id', 'content_sha256')}
assertion = lambda text: {'text': text, 'origin': 'user_assertion', 'refs': []}
card = {
    'objective': assertion('Prepare a rollback review.'),
    'constraints': [assertion('Do not execute the rollback.')],
    'decisions': [{'text': item['text'], 'origin': 'source_evidence', 'refs': [ref]}],
    'questions': [],
    'next_actions': [assertion('Ask the operator to review the evidence.')],
}
Path('required.json').write_text(json.dumps([ref]))
Path('task.json').write_text(json.dumps(card))
PY
kre context rollback --required required.json --budget 4000 --max-bytes 4000
kre task-checkpoint rollback-review --card task.json
kre task-resume rollback-review
```

Required context is a separate `kre-required/1` wrapper around the unchanged
context `0.1` envelope. Known required references are validated and packed before
optional search results. An unavailable reference yields
`REQUIRED_EVIDENCE_MISSING`; a reference that cannot fit yields `BUDGET_TOO_SMALL`.
Both produce empty context. Missing, private, revoked or nonexistent references
receive the same unavailable classification. A newer revision is never silently
substituted.

`source_evidence` entries must exactly reproduce their referenced excerpts.
`user_assertion` entries remain labeled assertions; `model_inference` entries
remain unverified and require references. KRE generates no new prose. Task cards
have a 32 KiB bound, at most 16 entries per list, 8 KiB per entry, eight references
per entry and 32 unique references overall. Resume output is capped at 128 KiB.

## Update, revoke and resume

```sh
printf '# Release\n\nRollback restores the cobalt snapshot after operator approval.\n' > example-docs/runbook.md
kre ingest example-docs/runbook.md --root example-docs --source-id runbook
kre context rollback --budget 4000
kre task-resume rollback-review
kre lifecycle runbook --action revoke
kre context rollback
kre task-resume rollback-review
```

The edit creates a new revision. The earlier revision remains inspectable as
superseded, but a saved task decision depending on it is excluded on resume.
Revocation excludes the current source too. Resume revalidates references and
removes entire dependent entries, including their prose. It cannot infer an
undeclared dependency in arbitrary assertion text.

`--historical` permits superseded or stale evidence, never revoked/deleted
material. Task resume always uses current eligibility. `lifecycle --action delete`
is a logical tombstone, not physical erasure of snapshots, SQLite journals,
backups or text already exported to a conversation.

Freshness, authority, origin and egress are separate source policy:

```sh
kre update-policy SOURCE_ID --freshness stale
kre update-policy SOURCE_ID --freshness fresh
```

Use an eligible, non-revoked source ID. A new timestamp does not make a source
more authoritative. Re-ingestion preserves established policy; trusted operators
change it explicitly. Defaults are `unknown` freshness, `unverified` authority,
`source_evidence` origin and `local_only` egress.

## Bounded context and honest uncertainty

Use `--budget`, `--max-bytes` and `--max-items` together. The local token estimate
counts UTF-8 bytes conservatively; it is not billed model usage. Citation and
source-state labels count toward context. KRE keeps source-corresponding passages
whole rather than cutting arbitrary bytes to fit.

`status: ok` means retrieval executed. `coverage: unknown` does not certify
completeness. Known packing omissions describe rejected candidates, not all
missing task facts. Lexical matches can be irrelevant, and paraphrases can miss.
`NO_EVIDENCE` means no eligible evidence was selected. A consumer must abstain or
request more evidence when the context does not support the task.

For direct model prompts, insert `context_text` once. Keep `items` for citation
inspection and reference extraction. Revalidate immediately before use after
knowledge changes; revalidation is a snapshot check, not an atomic lock around a
later model call. The consuming host owns egress and model permissions.

## Disable and uninstall

Stop using the CLI/library. For MCP, remove or disable only the KRE binding in the
client; its stdio child process exits when the client closes it. There is no
service, scheduler or listener to uninstall.

```sh
python -m pip uninstall knowledge-retrieval-engine
```

Uninstallation leaves your knowledge database intact. Back up or remove that
owned database separately when intended; retained copies/journals/backups need
their own handling. Do not remove other applications' databases or change their
configuration. The offline verification script creates and removes only its own
temporary files and MCP processes.
