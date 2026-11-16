# Frozen synthetic evidence evaluation

**Readiness status:** the user explicitly authorized analysis and improvement
against these original held-out cases after K2 completed. They are now a tuning
set. Current reports mark `independent_holdout: false`; they cannot support an
independent generalization claim. Original fixtures, split, hashes and K2 raw
results remain unchanged. The public [benchmark methodology](../docs/BENCHMARKS.md)
distinguishes these tuning results from later independent evaluation and actual
model-usage measurements.

This small K2 evaluation measures retrieval evidence, not generated answers or general semantic competence. It uses 21 fictional sources, 4 development cases and 24 held-out cases. The same corpus is available to both splits; their queries and gold spans are disjoint. The held-out queries and source/version/line-span labels were frozen before execution or tuning against their outcomes. `freeze.json` records the original UTC timestamp and SHA-256 hashes. The evaluator refuses changed fixtures. Do not adjust these cases to improve a score. A genuine fixture defect requires an explicitly recorded new version; retain the old evidence.

From the repository root, with the independent KRE package installed or `PYTHONPATH=src`:

```sh
PYTHONPATH=src python scripts/evaluate.py --split development --output development.json
PYTHONPATH=src python scripts/evaluate.py --split held_out --output held-out.json
```

The default is five measured warm calls per algorithm/case, after one warmup. `--repetitions` accepts 1–20. Measured call order alternates to reduce systematic order effects. Temporary SQLite state is created under `.scratch` and removed. No provider, network, embedding, model, credentials or external document is involved. Evaluation files/scripts are development artifacts, not a runtime dependency of KRE.

## Labels and metrics

Gold labels identify immutable source versions and line spans, independently of current chunk IDs. A retrieved excerpt covers a gold span only when its source and revision match, its quoted lines contain the whole span, and the citation is exact. The denominator is the number of declared gold spans, not the number of generated chunks.

- **Span precision:** returned excerpts that cover at least one gold span divided by all returned excerpts. **Span recall:** covered gold spans divided by all gold spans.
- **Source precision:** returned source IDs appearing in the gold labels divided by returned source IDs. **Source recall:** gold source IDs whose labeled evidence was actually covered divided by gold source IDs. Span metrics therefore distinguish an irrelevant heading from the fact in the same source.
- **Citation accuracy:** the source/revision/chunk exists and the cited line interval exactly matches the immutable normalized source text and SHA-256. This does not certify the truth or authority of the statement.
- **Policy checks:** unauthorized/revoked items, stale or superseded evidence in current-answer mode, fresh-only violations, and incorrect authority/origin/freshness/lifecycle/egress labels.
- **Required evidence:** actual delivered exact references, explicit missing reports, expected denial/budget codes and all-or-none behavior. Symbolic frozen source spans are resolved to actual host references before the measured request; that preparation is outside query latency.
- **Budgets:** actual UTF-8 bytes including citation metadata, conservative estimated-token accounting, maximum item count and the transport ceiling. Byte counts are not provider token counts.

A zero denominator is `null`, not a perfect score. Quality aggregates report 14 achievable positive-gold held-out cases separately from deliberately impossible required-reference/budget controls. All 24 cases remain in the per-case output. All-case precision and empty-gold cases returning excerpts make irrelevant retrieval visible. No relevance threshold turns a low score into a test failure; citation/privacy/freshness/accounting/required-contract defects do make the evaluator exit unsuccessfully.

The cases cover exact facts, irrelevant collisions, partial and synonym-only paraphrases, multi-source evidence, contradictory structured records, unknown/stale freshness, current/historical versions, revocation, missing information and private scopes. Contradictions are labeled examples whose source assertions must remain distinguishable. This evaluator does not claim to implement semantic contradiction detection.

## Baseline and context-size comparison

The simple baseline ranks the same eligible stored chunks by the number of distinct query tokens they contain, breaking ties by stored chunk ID. It does not read gold labels. Both methods use the same host scopes, source lifecycle/freshness eligibility, required references, candidate ceiling (`4 × max_items`), required-first greedy packing, item/byte limits and citation serialization. The baseline scans eligible rows; KRE uses its FTS5/BM25 index. The baseline's case-folded Unicode word matching and SQLite's tokenizer are explicitly different lexical methods.

The baseline shares only the neutral envelope/citation formatter with KRE; it does not reuse the FTS query or ranking. Independent citation checks compare both outputs to the frozen source text. Timing includes local query/admission/packing/serialization; it excludes source/ref preparation, process startup, network, harness and inference overhead. This small warm measurement is not a general performance benchmark.

Context sizes are compared only for positive-gold cases where **both methods deliver every labeled span and every required reference**. Smaller output with missing required evidence never earns a size improvement. Equal labeled evidence is still not proof of equal generated-answer quality.

## Original K2 held-out observation

The first frozen run had 21 sources and 49 chunks on Python 3.14.6 / SQLite 3.53.4. Micro span recall was 16 of 18 achievable gold spans for KRE (88.9%) and 17 of 18 for the overlap baseline (94.4%). Macro recall (the mean of the 14 positive-case recalls) was 89.3% and 92.9%, respectively. All-case span precision was 31.4% and 34.7%, respectively. Both missed the synonym-only case; KRE also missed one span in the multi-source case. An empty-gold fresh-only case still returned unrelated allowed material, demonstrating why lexical matches do not establish adequate evidence.

Both methods produced exact citations for every returned excerpt, with zero observed scope/revocation/freshness/label/budget violations in this finite corpus. Of nine required references, three were delivered; six were explicitly undelivered by the designed missing/private/superseded/budget controls. No required evidence silently disappeared.

On the 12 equal-coverage cases, median context was **1,746 bytes for KRE versus 1,466.5 bytes for the baseline**. This result provides no context-saving claim. Warm KRE latency was p50 0.1114 ms / p95 0.1823 ms; baseline p50 0.1917 ms / p95 0.2607 ms. Repeated measurements can differ with host activity. No tuning followed these observations during K2. The subsequent readiness authorization permits the explicitly disclosed tuning described above.

The milestone evidence contains the complete per-case JSON, returned excerpts, missing-reference reports, budget checks and raw latency samples. Evaluator tests use separate tiny examples plus the development split to check metric integrity. Readiness adds two fixed-cohort comparison tests; they do not assert target quality scores for the tuning cases.
