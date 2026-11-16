# Alpha retrieval decision

**Retain the runtime at 8318473. Reject bounded-neighbor windows for this alpha.** One deterministic proposal was locked before independent cases were evaluated. It improved the previously observed fragmented cases, but did not improve independent evidence recall, added context and lost a known tight-budget span. No second optimization cycle or model inference followed.

## Root cause and one evaluated correction

The six substantive historical misses were all in sources already discovered: three item-limit failures, two zero-lexical-match passages and one candidate cutoff. They were not caused by source permissions, freshness or corrupted citations. Five additional strict misses contained the annotated nonblank text but lacked intervening blank lines; four spans were correctly withheld by destination policy. These distinctions do not change the frozen 17/32 score.

The proposal retained ingestion and BM25 source discovery, then considered only the immediate preceding and following stored passage around each lexical hit. An expanded exact source window could contain at most three chunks and at most the existing 1,200-byte normal chunk target. It kept source/revision identity, included original blank lines, avoided repeated represented chunks and fell back to the original hit if expansion could not fit. It introduced revision-bound window references. No gold spans, question-specific terms or threshold sweep informed selection. [Locked rules](method-lock.json) and the [rejected patch](rejected-neighbor-windows.patch) preserve the experiment.

SQLite FTS5 supplies lexical matching and BM25 ordering, not semantic completeness. Neighboring paragraphs can restore local context, but cannot reliably identify which nonmatching passage a task needs. [SQLite FTS5 documentation](https://www.sqlite.org/fts5.html).

## Offline comparison

| Evaluation | Retained runtime | Rejected proposal | Context bytes retained → proposal |
|---|---:|---:|---:|
| Known 24 tasks, 16K selection budget | 63/63 | 63/63 | 286,022 → 304,009 (+6.29%) |
| Previously observed fragmented suite | 17/32 strict | 26/32 strict | 37,381 → 47,462 (+26.97%) |
| Known tasks at 8K | 60/63 | 60/63 | 162,128 → 164,240 |
| Known tasks at 4K | 59/63 | 58/63 | 79,357 → 80,076 |
| New independent ordinary-query cases | 24/28 | 24/28 | 34,923 → 35,651 (+2.08%) |

Known-suite bytes are the frozen benchmark's model-visible context representation. Fragmented/new-suite bytes are native citation-bearing JSON context. Compare within rows, not across unlike representations. Estimated tokens in the native contract are conservative UTF-8 byte counts, not model-billed tokens. No new actual token or answer measurements exist.

The old fragmented proposal's 26/32 divides into 26 strict spans, one blank-line-only gap, one substantive missing passage and four policy-withheld spans. Thus five of the six substantive misses were recovered, but this is a diagnostic on already-known cases, not independent generalization.

The new fixture was authored separately: 16 cases, 32 documents, 31 annotated spans. Ordinary queries contribute 28 spans; declared-required-reference controls are reported separately. Both runtimes supplied complete evidence on 10/12 positive ordinary cases, returned 42/42 exact citations, and had source precision 15/21. Neither produced policy or budget violations. Required-reference fit/failure and checkpoint/revoke/resume controls passed. A hard paraphrase and tight-budget case missed evidence in both. See the independent evaluation report for individual results and timing.

The author saw introductory README material during API discovery, but did not see the proposed method or earlier question content before authoring. This is independent case construction by another engineering agent, **not independent human semantic review**. The first evaluator incorrectly searched for raw multiline text inside serialized JSON. First outputs and the original evaluator freeze were retained; a disclosed rendering-check correction rescored saved outputs by parsing JSON, without changing queries, gold or retrieval. A separate offline continuation control completed the checks that the faulty rendering gate had skipped.

## Why the proposal is not shipping

The independent set showed no recall improvement, while context grew. The 4K known-suite regression and changed chunk/reference behavior introduce additional compatibility cost. Improving an already-known score does not justify those costs. The runtime, shared context contract and frozen benchmark scoring remain unchanged. The patch is research evidence, not an optional runtime mode.

## Supported alpha scope

KRE offers local lexical retrieval, exact immutable citations, declared source lifecycle/freshness and destination restrictions, bounded context and extractive task continuity. It is useful when documents and queries share vocabulary and callers inspect evidence. It is not a universal question-answering or semantic memory system.

`coverage: unknown` does not mean sufficient evidence. `partial` reports observed packing omissions; `NO_EVIDENCE` means no matching candidates. A nonempty result cannot reveal every missing semantic requirement. Use explicit required references when the caller already knows essential evidence; missing or unfit required references fail rather than silently disappear. Small budgets, long fragmented sources, paraphrases and mixed local/remote eligibility remain documented limitations.

Keep the original 96-call baseline immutable. Independent human review is still incomplete; LS04 and LS05 mechanical regressions remain. Retrieval correctness and context selection do not establish whole-workflow quality-preserving token, time or monetary savings. Recommend a narrowly described experimental alpha, subject to ordinary installation, security and license gates, without another retrieval refactor.
