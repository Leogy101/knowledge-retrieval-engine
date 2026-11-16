# Frozen synthetic alpha holdout

This suite measures deterministic local retrieval, exact citations, policy boundaries, budgets, and task continuity. It contains 16 fictional cases, 32 documents, and 31 gold spans. Six cases require at least three separate passages; document sizes range from 108 to 4,939 UTF-8 bytes. It does not generate answers. Human semantic review remains **unknown**; there is no claim of independent human review, provider-token savings, or semantic answer accuracy.

The questions, source bytes, exact gold source/character/line spans, trusted labels, budgets, and expectations were authored and frozen before retrieval. The proposed algorithm was separately locked before case contents were disclosed. No earlier case documents or retriever code were inspected by the case author. An input-shape README read unintentionally exposed prior correction descriptions, a documented chunk-size limit, and aggregate benchmark summaries; administrative messages also exposed earlier aggregate results. This limited exposure is disclosed and precludes a claim of complete informational isolation. The fixture was not tuned on retrieval results.

The original frozen artifacts are preserved under `original-freeze/`. Their manifest SHA-256 is recorded in `provenance.json`. The operative fixture has the same bytes and SHA-256 as that original freeze. The current `evaluate.py` contains one disclosed implementation correction: it decodes the JSON in `context_text` and verifies equality with `items`, instead of searching for unescaped multiline source text inside escaped JSON. That incorrect substring check falsely rejected valid citations in the first outputs. Source-span, source-ID, eligibility, budget, and completeness rules were not relaxed. Saved first responses were rescored without retrieval reruns. Because the erroneous gate skipped the first task-continuity exercise, a separately authorized unchanged-case continuity check ran once per version. Original full-artifact hashes and sanitized public-projection hashes are retained in `provenance.json`.

Ordinary requests contain only the frozen question and request options. They receive no gold text, expected source IDs, or forbidden-source IDs. Two caller-declared required-reference cases use a separately reported quote/source bootstrap and `context_required`; they do not enter ordinary retrieval recall.

Each source tree is imported in its own isolated Python subprocess, with a fresh temporary SQLite database for each case and network/subprocess audit events denied inside the worker. Ingestion and querying use the public Store API. Source inventories are hashed before and after the original runs. Baseline and candidate processes ran concurrently, so single-run submillisecond latency values should not be interpreted as comparative performance evidence.

The frozen scoring rules are:

- A gold span counts only when one exact, eligible returned item from the same source and immutable revision includes the complete unchanged quote and covers its frozen line interval. The response must succeed, validate current, and contain no policy violation. Execution failures remain in the denominator. No relaxed whitespace, semantic matching, or joined-passage scoring is used.
- Citation checks verify exact source lines, returned-text hashes, source/revision identity, trusted labels, nonempty unique IDs, JSON rendering equality, and direct Store snapshot validation. The final source newline may be included or omitted; no interior whitespace is rewritten. A particular chunk-ID format is not required.
- Source precision counts distinct gold-source incidences divided by all distinct returned-source incidences. Missing-answer cases contribute false-positive sources. A correct source alone does not establish support for every required fact.
- Context cost is full rendered UTF-8 bytes, including labels and citations. Conservative byte estimates are reported separately from provider tokens, which are unknown. Byte/token/item ceilings and reported accounting are checked.
- Private, revoked, disallowed superseded/stale, and destination-restricted evidence cannot earn credit. Historical superseded evidence is permitted only in the historical request. Local-only remote control must return an explicit empty-context error.
- Missing-answer control must not claim sufficient coverage. Unrelated matches are reported; `ok`/`unknown` does not certify an answer. The conflict case requires both contradictory statements without claiming the engine resolved them.
- Tight-budget missing spans remain completeness failures even when the ceiling is respected. The declared-reference tight-budget control separately requires empty `BUDGET_TOO_SMALL`.
- Continuity requires exact source evidence to survive an initial resume, then disappear after revocation with explicit invalidation while an independent assertion remains. The prior context must stop validating current.

The primary retrieval denominator is 28 spans across 12 ordinary positive cases. Two additional ordinary controls test absent evidence and remote denial. The two declared-reference cases are a separate stratum: two deliverable spans and one intentional budget failure. The all-case aggregate is diagnostic, not a single answer-success rate.

The prototype was rejected. Baseline runtime `8318473` was retained. These cases are now regression fixtures, not an untouched future holdout. `test_holdout.py` allows improvement while requiring at least 24/28 ordinary spans, at least 10 complete positive cases, and all citation, budget, policy, required-reference, and continuity checks.

For a fresh reproduction, use a new output path and the bundled lock hash:

```sh
python3 evaluate.py --source-root /path/to/checkout \
  --revision-label reproduction --algorithm-lock method-lock.json \
  --expected-lock-sha256 LOCK_SHA256 --output reproduction.json
```

Compute `LOCK_SHA256` with a SHA-256 utility over `method-lock.json`. The evaluator refuses to overwrite a result or silently repeat the same source-inventory evaluation. To run the repeatable regression checks:

```sh
KRE_SOURCE_ROOT=/path/to/checkout python3 -B -m unittest -v test_holdout.py
```

When stored inside a checkout, the test can find an ancestor containing `src/kre` without the environment variable. The original private full artifacts are represented by their hashes; public projections remove local paths and retain all synthetic requests, evidence, metrics, failures, and continuity observations.
