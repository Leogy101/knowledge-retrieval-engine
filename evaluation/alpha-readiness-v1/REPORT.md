# Synthetic alpha holdout results

The prototype produced no evidence-recall improvement on the new frozen cases and increased context bytes. The decision was to reject it and retain baseline runtime `8318473`. This report covers deterministic offline retrieval; human semantic review and generated-answer quality remain unknown.

| Ordinary retrieval measure | Baseline | Prototype |
| --- | ---: | ---: |
| Exact gold spans | 24/28 (85.7%) | 24/28 (85.7%) |
| Complete positive cases | 10/12 | 10/12 |
| Source precision, all 14 ordinary cases | 15/21 (71.4%) | 15/21 (71.4%) |
| Source precision, positive cases only | 15/19 (78.9%) | 15/19 (78.9%) |
| Exact citations | 42/42 | 42/42 |
| Rendered context bytes | 34,923 | 35,651 |
| Reported conservative-byte token estimate | 34,923 | 35,651 |
| Compact serialized full-response bytes | 80,087 | 81,596 |
| Median retrieval call, ms | 0.218 | 0.258 |
| Nearest-rank p95 retrieval call, ms | 0.910 | 1.200 |
| Policy / budget violations | 0 / 0 | 0 / 0 |

Prototype ordinary context grew by 728 bytes, **2.08%**, with no newly recovered span. Single-run timing used concurrent isolated processes; it is descriptive only. Bytes are not measured provider tokens or monetary cost.

| Case | Stratum | Baseline spans | Prototype spans | Baseline bytes | Prototype bytes |
| --- | --- | ---: | ---: | ---: | ---: |
| H01 | Long fragmented museum procedure | 4/4 | 4/4 | 8,776 | 9,024 |
| H02 | Three-source pantry coordination | 3/3 | 3/3 | 2,464 | 2,464 |
| H03 | Current sensor guidance / obsolete controls | 3/3 | 3/3 | 3,596 | 3,695 |
| H04 | Fragmented cabinet relocation | 3/3 | 3/3 | 4,260 | 4,378 |
| H05 | Long event-access plan | 4/4 | 4/4 | 7,516 | 7,779 |
| H06 | Hard paraphrase | 0/1 | 0/1 | 681 | 681 |
| H07 | Conflicting notices | 2/2 | 2/2 | 1,352 | 1,352 |
| H08 | Short Unicode note | 1/1 | 1/1 | 1,215 | 1,215 |
| H09 | Missing-answer control | — | — | 1,397 | 1,397 |
| H10 | Private-scope exclusion | 1/1 | 1/1 | 637 | 637 |
| H11 | Local-only remote denial | — | — | 0 | 0 |
| H12 | Declared references, ample budget | 2/2 | 2/2 | 1,896 | 1,896 |
| H13 | Declared references, too-small budget | 0/1, safe error | 0/1, safe error | 0 | 0 |
| H14 | Initial task evidence | 1/1 | 1/1 | 1,264 | 1,264 |
| H15 | Historical/current lifecycle comparison | 2/2 | 2/2 | 1,303 | 1,303 |
| H16 | Ordinary tight budget | 0/3 | 0/3 | 462 | 462 |

The hard-paraphrase case retrieved a lexical distractor in both versions. The ordinary 700-byte budget supplied no substantive gold spans, despite staying within its ceiling and reporting partial coverage. The missing-answer case returned two unrelated sources in both versions, with coverage unknown; no generated abstention was tested. The conflict case recovered both contradictory notices, without establishing automated contradiction resolution.

The declared-reference stratum passes both controls: 2/2 known spans fit the ample budget, and the intentionally unfit required reference returns `BUDGET_TOO_SMALL` with empty context. Its three returned citations are exact. Both versions exclude private/revoked evidence, preserve the historical distinction, and return empty `DESTINATION_DENIED` for the remote request. Successful first-run context snapshots validate current; the two empty error envelopes validate denied.

The separate continuity check passes in both versions: exact evidence survives the first resume, revocation removes dependent prose with an explicit invalidation, the independent user assertion remains, and the old snapshot validates `changed`. This is a synthetic local checkpoint control, not evidence that a real agent recovered a task or produced a correct answer.

The first frozen evaluator contained a rendering-check defect: it searched unescaped multiline item text inside JSON-escaped `context_text`, falsely gating recall to zero. Those original outputs and the original freeze are preserved. The correction decodes JSON and compares the item arrays exactly; saved responses were rescored without retrieval reruns, with no gold or policy-rule change. One separately authorized continuity setup query per version completed the check the erroneous gate had skipped. See `provenance.json` for full-artifact and public-projection hashes and `METHODOLOGY.md` for limited README/aggregate-results exposure.

No inference ran. No provider usage or savings were measured. Exact citations and synthetic evidence availability do not replace human semantic review.
