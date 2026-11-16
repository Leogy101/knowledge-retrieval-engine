# Independent synthetic alpha holdout, version 1

This is an offline deterministic retrieval evaluation. It produces no model answers and makes no inference, provider, live-service, or network calls. Human semantic review is **unknown**. Exact support, citation fidelity, and lifecycle checks do not establish human answer correctness or general semantic completeness.

## Freeze and authoring

The fixture contains 16 newly written cases, 32 fictional documents, and 31 exact gold spans. Six cases require three or more separately authored passages. Documents range from 108 to 4,939 UTF-8 bytes. Their natural layouts include short notes, paragraphs, headings, widely separated sections, and longer unwrapped lines. Domains and proper names are synthetic. No source text was copied from earlier evaluations.

Questions, complete source bytes, trusted metadata, gold source IDs and exact character/line spans, budgets, purpose, destination, forbidden sources, declared-reference cases, and checkpoint mutation were fixed before any retrieval execution. `author_fixture.py` deterministically serializes these inputs; `fixture.json` is the operative frozen data. `freeze-manifest.json` hashes the fixture, authoring script, evaluator, and this methodology. Source spans were validated using ordinary string operations only; no evaluated package was imported during authoring.

The author did not inspect retriever code, existing task fixtures, previous fragmented-case documents, or the proposed algorithm. Input-shape discovery read the context 0.1 schemas and AST-extracted public method signatures. A broad README read unintentionally exposed its old correction summary, documented chunk-size limit, and prior benchmark summaries. An administrative agent inventory also exposed historical result summaries, but not case documents. This exposure is disclosed: the holdout is independent of actual previous case contents and was not tuned against retrieval results, but is not a claim of total informational isolation. The new fixture's authoring source was complete before the parent announced the implementation was ready; serialization followed immediately without changes. The parent had locked the proposed method before receiving any case content. Later parent messages supplied aggregate candidate outcomes while the evaluator was being completed; neither fixture nor scoring was changed in response to those outcomes.

## Inputs and execution isolation

Run `evaluate.py` once for each separately supplied source root. It requires a revision label, the pre-existing algorithm-lock path and exact SHA-256, and a new output filename. It verifies every frozen artifact before running. A package inventory is hashed before and after execution. A source-inventory-specific exclusive first-attempt marker prevents silently repeating a run. Output files cannot be overwritten.

Each evaluated source root runs in its own Python `-I -B` subprocess with an explicitly inserted `src` path. The worker confirms the imported package path and uses a fresh temporary SQLite database for every case. It calls only public `Store`/`evidence_ref` APIs. The process denies socket and subprocess audit events; no model, embedding, provider, server, or GPU inference is involved. Only the supplied local sources are indexed. Temporary databases are removed afterward. The raw request, response, references, lifecycle outputs, timings, and package provenance are retained.

The trusted host configures a shared reader scope and a broader owner scope for setup. Ordinary retrieval requests receive **only** the frozen question and contract request options. Gold text, expected source IDs, and forbidden source IDs never enter ordinary requests. Access filtering and destination policies are supplied as trusted metadata, not extracted from source prose.

Two cases explicitly model a caller already declaring known required references. They use a documented bootstrap: retrieve the exact known quote in its declared source with a generous budget, retain the returned immutable reference, then call `context_required` with the frozen final budget. Every bootstrap request and result is saved. Those cases are scored in a separate stratum and do not enter ordinary retrieval recall. Their bootstrap is not evidence of natural-language discovery performance.

## Frozen scoring rules

1. **Exact evidence recall:** each gold span is credited only when one returned item from its exact source and immutable ingestion revision includes the complete unchanged quote and covers its frozen line interval. The item must pass exact-text/hash/locator checks. The response must be successful, have a current `Store.validate_context` result, and contain no policy violations. Error responses and execution failures earn zero coverage. All expected gold spans remain in denominators even on execution failure. No blank-line relaxation, synonym credit, passage union, or post-run gold editing is allowed.
2. **Source precision:** numerator is distinct returned gold-source IDs per case; denominator is distinct returned source IDs per case. Micro-aggregation sums those source incidences. A correct source with an irrelevant passage can still count toward source precision, which is why exact span recall is also mandatory. Cases with no gold retain their false-positive sources in the ordinary aggregate. Empty returned-source sets have undefined individual precision, not an automatic perfect score.
3. **Exact citations:** returned source/revision IDs, whole cited line slice, text SHA-256, nonempty unique citation IDs, nonempty chunk IDs and recorded timestamps, metadata labels, and rendered inclusion of item text/citation ID are checked. The final line's newline delimiter may be included or omitted; no interior text is normalized. Public `Store.validate_context` provides additional implementation-level immutable-reference and snapshot validation. The scorer does not require a particular chunk-ID grammar or stored chunk shape, and therefore can evaluate exact source windows. It does not independently authenticate timestamp history.
4. **Context cost:** UTF-8 bytes of the full `context_text` are measured directly, including citations and labels. Estimated tokens are reported as the package labels them; conservative-byte counts must equal rendered bytes. A separately defined compact UTF-8 JSON serialization measures full response bytes. These are not provider tokens, total model-view bytes, inference costs, or savings.
5. **Budgets:** rendered byte, estimated-token, and item ceilings are checked, as are reported byte totals, citation accounting, and empty error responses. A tight-budget case is one whose frozen token budget is at most 800. Its uncovered required spans are a tight-budget completeness failure even when the engine correctly stays within the ceiling. Safe rejection and evidence completeness are reported separately.
6. **Policy:** private collection, revoked content, superseded/stale current evidence, destination restrictions, requested freshness, and explicitly forbidden sources are checked before evidence credit. Historical superseded evidence is allowed only in the historical case; revoked evidence is never allowed. A remote request whose only relevant source is local-only must return an explicit error with empty evidence. Error codes are retained rather than renamed.
7. **Missing evidence:** the missing-answer case has no gold. Unrelated returned items are counted as unsupported context and false-positive sources. Any `coverage:sufficient` is a failure. An operation reporting `ok`, `partial`, or `coverage:unknown` is never interpreted as proof that the answer is supported. No generated abstention is scored because no answer is generated.
8. **Conflict:** both independently issued contradictory statements are required. Recovering them demonstrates evidence availability, not automatic contradiction resolution or correctness of a generated explanation.
9. **Declared references:** the ample-budget case must supply all declared spans without wrapper error. The tight-budget case must return `BUDGET_TOO_SMALL` with empty evidence. Its safe failure is a successful control, not positive evidence recall.
10. **Continuity:** the normal query must first recover its gold evidence. A returned item containing that evidence is then checkpointed as exact `source_evidence`, alongside an independent `user_assertion`. Resume must retain it before revocation. After revocation, dependent prose must be absent, invalidation visible, the independent assertion retained, and the old context no longer current. The task API receives returned evidence only; it never receives a fabricated gold-based answer. Setup failure remains a continuity failure.
11. **Latency:** one measured context call per case, with indexing/setup reported separately. Declared-reference bootstrap and task operations have separate timings. Aggregate median and nearest-rank p95 describe this single small local run, not a warmed throughput benchmark or an inference latency claim.

The primary strata are ordinary positive retrieval, all ordinary cases including policy/missing controls, explicitly declared required references, and policy/missing controls. The all-case aggregate is diagnostic only because required-reference failure controls intentionally differ from answerable queries. Per-case outcomes remain available; no adverse case may be dropped or reclassified after execution.

## Expectations by case type

- Answerable ordinary and conflict cases seek all frozen gold spans and exact, eligible citations within the supplied budget.
- The ordinary tight-budget case retains the same completeness requirement; missing spans expose the limitation even if rejection is safe.
- Missing-answer control requires no false sufficiency claim; unrelated context is explicitly reported.
- Private and historical cases must retrieve allowed evidence without forbidden sources.
- Local-only remote control requires a safe, explicit empty-context error.
- Required-reference cases distinguish successful declared evidence delivery from safe budget failure.
- Continuity requires initial evidence plus retain-then-invalidate behavior.

No algorithm, corpus, question, gold, budget, or scorer tuning is permitted after the first run. Any evaluator defect must be disclosed with its original output preserved; results cannot be silently repaired or rerun. The report must preserve human semantic review as unknown.

## Reproduction

```sh
python3 evaluate.py --source-root /path/to/locked/checkout \
  --revision-label locked-label \
  --algorithm-lock /path/to/method-lock.json \
  --expected-lock-sha256 EXPECTED_SHA256 \
  --output /path/to/new-results.json
```
