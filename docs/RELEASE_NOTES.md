# KRE 0.3.2a1 — experimental alpha

KRE retrieves authorized local evidence with exact citations and preserves task
dependencies across source changes. It runs independently with Python and SQLite,
without a model, cloud provider, embeddings, background server or GCB dependency.

The supported workflow is install → ingest explicit text/Markdown files → search
or retrieve bounded context → inspect citations → update/revoke → checkpoint and
resume with revalidated evidence. Optional MCP exposes fixed-scope retrieval and
validation to an existing compatible client. No OpenClaw configuration is changed
by installation, and no native governed routing is enabled.

Use the five-minute README quickstart and `scripts/verify_user_workflow.py` after
installation. Safe file ingestion currently requires POSIX filesystem primitives.
Only platforms/Python versions actually passing release verification are claimed;
a CI file alone does not establish support.

This is an experimental retrieval product, not a completeness guarantee or a
promise of lower model bills. The original 96-call comparison retained missing
evidence, compact-document token overhead and two mechanical quality regressions.
Independent semantic review of all 96 answers is still pending. Offline coverage
improvements do not change historical answers or establish new model-token savings.

A focused same-source retrieval prototype was rejected after new independent
cases showed no recall improvement, context growth and one tight-budget
regression. The accepted runtime remains unchanged from `8318473`; no speculative
retrieval feature is included.

Version `0.3.2a1` and release tag `v0.3.2a1` match the existing package metadata.
Apache-2.0 is adopted with designated CC0 dataset terms and companion attribution.
The initial release uses a dependency-free text wordmark. Distribution is an
experimental GitHub prerelease; no PyPI publication is included. The release
process verifies both main-branch and tag CI before uploading assets.
See [executed verification](VERIFICATION.md) for platform scope and the remaining
optional test skip. No new live inference was used for release verification.
