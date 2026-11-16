# Alpha candidate verification

The retained runtime is byte-identical to 8318473. No new model inference or live host configuration change was performed. The table below records the local prepublication checks. Current public checks are available in [GitHub Actions](https://github.com/Leogy101/knowledge-retrieval-engine/actions). Release publication additionally requires every declared main/tag job, fresh public installation and successful code scanning; release provenance records the qualified runs.

| Environment | Public regression suite | Installed workflow | SQLite / FTS5 |
|---|---|---|---|
| macOS 26.3.1 arm64, Python 3.11.15 | 314 run, 313 pass, 1 expected skip | 24/24 | 3.53.4, available |
| macOS 26.3.1 arm64, Python 3.13.1 | 314 run, 313 pass, 1 expected skip | 24/24 | 3.45.3, available |
| macOS 26.3.1 arm64, Python 3.14.6 | 314 run, 313 pass, 1 expected skip | 24/24 | 3.53.4, available |

The skip is the optional version-matched public OpenClaw-source replay, which requires a separately supplied public package and Node. Its retained synthetic host-attribution fixture is still checked. Runtime use does not require that package. The earlier private original suite passed 306 methods (305 pass, the same skip) on these three Python versions; final publication preparation leaves that repository unchanged and reruns the public suite. Ten new alpha tests cover independently authored retrieval cases, the shared contract and private archive-header removal. Two archival private-payload checks remain private; see [public test scope](../PUBLIC_TEST_SCOPE.md). No security or authorization test was removed to obtain a pass.

The main test process and ordinary CLI/MCP subprocesses use the installed wheel. Six frozen alpha holdout methods retain their existing source-checkout evaluator worker; all 13 runtime files (12 Python modules and one sample document) in the wheel match the checkout byte for byte. Those six methods were run, not skipped.

Each installed-wheel walkthrough runs from temporary storage using the installed package, with no source-tree import path or private helper. It verifies init, demos, explicit-root ingestion, search, bounded context, exact citations, revision inspection, required-evidence errors, real MCP stdio discovery/retrieve/validate, rejected scope expansion, child-process exit, immutable update, revocation, and checkpoint/resume invalidation. Package uninstall is checked separately and leaves no integration process or installed module.

The eight-command README quickstart passed in a clean Python 3.11.15 environment (3.035 seconds observed; installation may obtain build dependencies). Full suite times were 2.175, 2.185 and 2.414 seconds for Python 3.11, 3.13 and 3.14 respectively; installed workflow times were 0.970, 1.016 and 1.171 seconds. These are one local verification run per environment, not general performance targets.

The GCB companion's independently retained context0.1 schemas and fixtures match byte for byte. Its existing validator accepts a generated KRE context and rejects tampered text. KRE's tests and installation do not import or require GCB. The wire contract is unchanged.

The CI workflow targets full offline suites on macOS/Linux with Python3.11–3.14, plus a named Windows portable-core subset. Platform support is established by the corresponding completed jobs, whose exact runner images and Python versions are recorded with the release. A workflow declaration alone is not evidence. Windows protected file ingestion is unsupported and must fail closed. CI uses read-only repository permissions, pinned official actions, no inference credentials and no privileged pull-request execution.

The public snapshot is allowlisted and has no private Git ancestry. Its source manifest and release checker provide drift/signature checks, not a guarantee against every secret. Wheel, source distribution and complete source archive are inspected separately. An audit caught local owner/group names in generated sdist headers; the reproducible packaging step now removes that metadata without changing payload bytes. Apache-2.0 and attribution are adopted; final artifacts are rebuilt and checked for all five license files. The wheel contains Apache-2.0 software; source artifacts also carry the designated CC0 corpus. See [licensing metadata](../LICENSING.md) for the intentionally omitted single static License-Expression. The initial release uses a plain-text wordmark without graphical logos or font files.

See [machine-readable local checks](VERIFICATION.json), [retrieval decision](alpha/RETRIEVAL_DECISION.md), [independent evaluation](../evaluation/alpha-readiness-v1/REPORT.md), and [historical measurements](benchmarks/historical-96.md). Whole-workflow quality-preserving savings and independent human semantic approval remain unproven.

The standalone local measurement helper's release-version label was corrected to
read the installed package version. It now reports 200 actual stored chunks from
200 small documents. Its original exact-single-line metric remains 0/40 because
these sources are retained whole; an explicitly separate source-line-containment
metric reports 40/40. This diagnostic addition changes no frozen benchmark score
and establishes no generalized recall or efficiency claim.
