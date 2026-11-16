# Contributing

KRE aims to provide useful local evidence with exact provenance and modest dependencies. Keep proposed changes small and explain the user-visible problem they solve.

## Development

Use Python 3.11 or newer with SQLite FTS5. In a virtual environment:

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

The full file-ingestion test matrix targets macOS and Linux. Windows CI targets the portable core only; it does not imply support for POSIX file ingestion. A declared matrix is not evidence of a passing platform until the required jobs have executed.

Tests and examples must use synthetic or redistributable public data. Do not invoke model providers, require personal credentials, install a live host integration or modify a user's environment as part of automated tests. The core must remain usable without GCB, embeddings, a model provider or a background service.

## Correctness requirements

- Preserve exact source spans, immutable revisions, source hashes and citation provenance.
- Filter access, lifecycle, freshness and destination policy before returning evidence.
- Keep required evidence explicit. Report insufficient budget rather than silently dropping required references.
- Revalidate task evidence on resume; never restore revoked material.
- Count rendered context, including citation metadata. Treat local token estimates separately from provider usage.
- Preserve the versioned interoperability contract unless a deliberate new version is warranted.
- Keep missing measurements and incomplete semantic review unknown.

Add targeted regression tests for a demonstrated defect. Evaluate retrieval changes against both prior cases and fresh held-out cases. Freeze task inputs, source revisions, expected spans and scoring before evaluation. Preserve failed results and historical measurements; do not adjust a frozen benchmark after seeing its answers.

A larger context or higher evidence recall alone is not proof of overall efficiency. Report quality, context size and latency together. Actual model-token or monetary savings require comparable, complete measurements and preserved answer quality.

## Pull requests

Describe the problem, the resulting behavior and the checks you ran. Document known limitations. Include no private paths, account identifiers, personal source documents, agent configurations or operational logs. Report security issues through the process in [SECURITY.md](SECURITY.md).

Software and documentation contributions are submitted under Apache-2.0 unless explicitly stated otherwise. Preserve the existing CC0 dedication for designated dataset contributions. Only submit material you have the right to distribute; retain applicable third-party notices. See [LICENSING.md](LICENSING.md) and [NOTICE](NOTICE).
