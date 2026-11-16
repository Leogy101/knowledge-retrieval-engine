# Historical KRE benchmark: consumption and unresolved quality

96 local content-generating calls covered 24 frozen synthetic tasks, two conditions and two models. Each arm used `think:false`, a 32K requested context profile and a 1,536-token output ceiling. There were no retries or answer repairs. All 48 pairs have complete Ollama-reported input/output usage. This is the historical runtime `74ee976`; later offline retrieval corrections have not been measured with new model calls.

**Quality-preserving efficiency is not established.** All 96 independent semantic reviews remain unknown. No automated reviewer or implementation self-review is substituted. Mechanical failures are retained; passing a mechanical gate does not establish factual correctness, task completion or citation-to-claim support.

## Measured token consumption, separated by baseline

| Model / baseline | Pairs | Input tokens disabled → enabled | Output tokens disabled → enabled | Total tokens disabled → enabled | Observed token reduction | Required evidence disabled → enabled | Mechanical gates disabled → enabled |
|---|---:|---:|---:|---:|---:|---:|---:|
| qwen3.5:9b / complete_documents | 6 | 18,490 → 20,027 | 1,988 → 1,900 | 20,478 → 21,927 | -7.08% | 16/16 → 14/16 | 2/6 → 4/6 |
| qwen3.5:9b / window_fts5 | 18 | 78,077 → 64,283 | 7,307 → 5,364 | 85,384 → 69,647 | 18.43% | 44/47 → 39/47 | 7/18 → 12/18 |
| qwen3.6:35b-a3b / complete_documents | 6 | 18,490 → 20,027 | 2,029 → 1,840 | 20,519 → 21,867 | -6.57% | 16/16 → 14/16 | 3/6 → 4/6 |
| qwen3.6:35b-a3b / window_fts5 | 18 | 78,077 → 64,283 | 5,879 → 6,305 | 83,956 → 70,588 | 15.92% | 44/47 → 39/47 | 9/18 → 13/18 |

Positive reduction means fewer observed tokens; negative reduction is a consumption regression. No combined headline mixes the complete-document and constrained FTS5-window baselines. These are small finite synthetic strata, with one sample per arm. They do not test an unrestricted advertised context window or establish population-level significance.

## Timing and context

| Model / baseline | Completion seconds disabled → enabled | Inference seconds disabled → enabled | Supplied context bytes disabled → enabled | Submitted message-text bytes disabled → enabled | KRE retrieval seconds (sum) |
|---|---:|---:|---:|---:|---:|
| qwen3.5:9b / complete_documents | 131.268 → 129.447 | 112.614 → 118.367 | 50,946 → 42,318 | 61,852 → 53,224 | 0.025189 |
| qwen3.5:9b / window_fts5 | 470.916 → 382.374 | 436.750 → 348.760 | 283,290 → 146,792 | 316,076 → 179,578 | 0.109383 |
| qwen3.6:35b-a3b / complete_documents | 140.368 → 145.845 | 37.741 → 40.756 | 50,946 → 42,318 | 61,852 → 53,224 | 0.021445 |
| qwen3.6:35b-a3b / window_fts5 | 432.213 → 411.770 | 139.925 → 124.970 | 283,290 → 146,792 | 316,076 → 179,578 | 0.088446 |

Times are sums of the retained per-arm measurements, not campaign wall time. The retained `completion_seconds` measures explicit preload through response processing, including context preparation but excluding preflight and cleanup. `full_arm_seconds` in the JSON additionally includes preflight and cleanup via receipt timestamps. Inference durations exclude explicit preload/unload operations. Retrieval is measured separately and is not an additional model call. 48 treatment retrievals total 0.244463 seconds (mean 5.093 ms, median 4.956 ms, maximum 8.316 ms). Submitted message-text bytes include instructions/wrappers; server-rendered chat-template bytes are unavailable. Smaller context serialization did not imply fewer provider-reported input tokens on compact tasks; actual billed charges remain unknown.

Input+output total 394,366 tokens across 96 calls; cached-token counters separately report zero and are not added again. Reasoning tokens, actual billed charges and estimated costs remain unknown. Local operation is not represented as a measured zero charge. Hardware: Apple M4 Pro, 14 logical CPUs, 64 GiB physical memory. Software: macOS 26.3.1, Python 3.14.6, Ollama 0.40.15.

Full-arm wall time, including preflight and cleanup (receipt timestamp differences):

| Model / baseline | Disabled seconds | Enabled seconds |
|---|---:|---:|
| qwen3.5:9b / complete_documents | 131.777 | 129.957 |
| qwen3.5:9b / window_fts5 | 472.550 | 383.881 |
| qwen3.6:35b-a3b / complete_documents | 141.927 | 147.424 |
| qwen3.6:35b-a3b / window_fts5 | 436.929 | 416.523 |

## Quality and regressions

All 96 outputs passed the frozen JSON/schema checks. Required supplied evidence per 24-task selection was 60/63 baseline versus 53/63 KRE for each model. The seven treatment failures were LS02, LS04, LS05, LS06, LS22, LS23 and LS24; LS06 also lacked baseline evidence. The later 63/63 offline correction does not revise these historical measurements.

35B LS04 changed from mechanical pass to fail: required evidence 3/3→2/3. 35B LS05 likewise regressed 4/4→3/4. Their emitted quotations were exact in both arms; omission of necessary evidence still failed the frozen overall mechanical gate. Both were retained as failures; subjective semantic conclusions remain unknown.

For each model, seven pairs had fewer tokens with both mechanical gates passing. Another four 9B/five 35B pairs used fewer tokens and changed mechanical fail→pass. These are candidate benefits for review, not proven quality-preserving benefits. Both models used more total tokens on LS01, LS04, LS07, LS10, LS13, LS19 and LS22. All 48 pairs remain inconclusive for end-to-end quality-preserving efficiency.

Exact quotation checks (not semantic citation support):

| Model / baseline | Exact quotations disabled | Exact quotations enabled |
|---|---:|---:|
| qwen3.5:9b / complete_documents | 7/16 | 19/19 |
| qwen3.5:9b / window_fts5 | 30/53 | 47/49 |
| qwen3.6:35b-a3b / complete_documents | 13/16 | 17/17 |
| qwen3.6:35b-a3b / window_fts5 | 36/45 | 56/56 |

## Every paired task

`P`/`F` denotes only the frozen mechanical gate. Every row has unknown independent semantic quality.

| Model | Task | Baseline | Tokens disabled → enabled | Reduction | Mechanical disabled → enabled | Supplied evidence disabled → enabled |
|---|---|---|---:|---:|---|---|
| qwen3.5:9b | LS01 | complete_documents | 3,426 → 3,656 | -6.71% | F → P | 3/3 → 3/3 |
| qwen3.5:9b | LS02 | window_fts5 | 4,944 → 4,033 | 18.43% | F → F | 2/4 → 1/4 |
| qwen3.5:9b | LS03 | window_fts5 | 4,590 → 4,036 | 12.07% | F → P | 4/4 → 4/4 |
| qwen3.5:9b | LS04 | complete_documents | 3,559 → 3,601 | -1.18% | F → F | 3/3 → 2/3 |
| qwen3.5:9b | LS05 | window_fts5 | 5,243 → 3,870 | 26.19% | F → F | 4/4 → 3/4 |
| qwen3.5:9b | LS06 | window_fts5 | 4,542 → 3,752 | 17.39% | F → F | 2/3 → 2/3 |
| qwen3.5:9b | LS07 | complete_documents | 3,365 → 3,658 | -8.71% | P → P | 3/3 → 3/3 |
| qwen3.5:9b | LS08 | window_fts5 | 4,854 → 3,687 | 24.04% | F → P | 3/3 → 3/3 |
| qwen3.5:9b | LS09 | window_fts5 | 4,879 → 4,108 | 15.80% | P → P | 3/3 → 3/3 |
| qwen3.5:9b | LS10 | complete_documents | 3,370 → 3,655 | -8.46% | F → P | 2/2 → 2/2 |
| qwen3.5:9b | LS11 | window_fts5 | 4,529 → 3,705 | 18.19% | F → P | 3/3 → 3/3 |
| qwen3.5:9b | LS12 | window_fts5 | 4,491 → 3,569 | 20.53% | P → P | 3/3 → 3/3 |
| qwen3.5:9b | LS13 | window_fts5 | 3,943 → 4,307 | -9.23% | F → P | 1/1 → 1/1 |
| qwen3.5:9b | LS14 | window_fts5 | 4,333 → 3,785 | 12.65% | P → P | 1/1 → 1/1 |
| qwen3.5:9b | LS15 | window_fts5 | 4,334 → 3,739 | 13.73% | F → F | 1/1 → 1/1 |
| qwen3.5:9b | LS16 | window_fts5 | 4,909 → 3,698 | 24.67% | P → P | 0/0 → 0/0 |
| qwen3.5:9b | LS17 | window_fts5 | 4,660 → 3,899 | 16.33% | P → P | 2/2 → 2/2 |
| qwen3.5:9b | LS18 | window_fts5 | 4,905 → 3,703 | 24.51% | P → P | 1/1 → 1/1 |
| qwen3.5:9b | LS19 | complete_documents | 3,327 → 3,580 | -7.60% | P → P | 2/2 → 2/2 |
| qwen3.5:9b | LS20 | window_fts5 | 4,777 → 3,771 | 21.06% | F → P | 3/3 → 3/3 |
| qwen3.5:9b | LS21 | window_fts5 | 5,206 → 3,879 | 25.49% | P → P | 4/4 → 4/4 |
| qwen3.5:9b | LS22 | complete_documents | 3,431 → 3,777 | -10.08% | F → F | 3/3 → 2/3 |
| qwen3.5:9b | LS23 | window_fts5 | 5,087 → 3,903 | 23.28% | F → F | 3/3 → 2/3 |
| qwen3.5:9b | LS24 | window_fts5 | 5,158 → 4,203 | 18.51% | F → F | 4/4 → 2/4 |
| qwen3.6:35b-a3b | LS01 | complete_documents | 3,347 → 3,574 | -6.78% | F → P | 3/3 → 3/3 |
| qwen3.6:35b-a3b | LS02 | window_fts5 | 4,914 → 4,139 | 15.77% | F → F | 2/4 → 1/4 |
| qwen3.6:35b-a3b | LS03 | window_fts5 | 4,655 → 3,977 | 14.56% | F → P | 4/4 → 4/4 |
| qwen3.6:35b-a3b | LS04 | complete_documents | 3,386 → 3,504 | -3.48% | P → F | 3/3 → 2/3 |
| qwen3.6:35b-a3b | LS05 | window_fts5 | 4,472 → 3,938 | 11.94% | P → F | 4/4 → 3/4 |
| qwen3.6:35b-a3b | LS06 | window_fts5 | 4,590 → 4,200 | 8.50% | F → F | 2/3 → 2/3 |
| qwen3.6:35b-a3b | LS07 | complete_documents | 3,402 → 3,771 | -10.85% | P → P | 3/3 → 3/3 |
| qwen3.6:35b-a3b | LS08 | window_fts5 | 4,858 → 3,771 | 22.38% | P → P | 3/3 → 3/3 |
| qwen3.6:35b-a3b | LS09 | window_fts5 | 4,893 → 4,045 | 17.33% | F → P | 3/3 → 3/3 |
| qwen3.6:35b-a3b | LS10 | complete_documents | 3,431 → 3,732 | -8.77% | P → P | 2/2 → 2/2 |
| qwen3.6:35b-a3b | LS11 | window_fts5 | 4,394 → 3,795 | 13.63% | F → P | 3/3 → 3/3 |
| qwen3.6:35b-a3b | LS12 | window_fts5 | 4,500 → 3,700 | 17.78% | P → P | 3/3 → 3/3 |
| qwen3.6:35b-a3b | LS13 | window_fts5 | 3,944 → 4,307 | -9.20% | P → P | 1/1 → 1/1 |
| qwen3.6:35b-a3b | LS14 | window_fts5 | 4,327 → 3,803 | 12.11% | P → P | 1/1 → 1/1 |
| qwen3.6:35b-a3b | LS15 | window_fts5 | 4,324 → 3,752 | 13.23% | P → P | 1/1 → 1/1 |
| qwen3.6:35b-a3b | LS16 | window_fts5 | 4,877 → 3,751 | 23.09% | P → P | 0/0 → 0/0 |
| qwen3.6:35b-a3b | LS17 | window_fts5 | 4,554 → 3,893 | 14.51% | P → P | 2/2 → 2/2 |
| qwen3.6:35b-a3b | LS18 | window_fts5 | 4,807 → 3,737 | 22.26% | P → P | 1/1 → 1/1 |
| qwen3.6:35b-a3b | LS19 | complete_documents | 3,340 → 3,568 | -6.83% | F → P | 2/2 → 2/2 |
| qwen3.6:35b-a3b | LS20 | window_fts5 | 4,686 → 3,768 | 19.59% | F → P | 3/3 → 3/3 |
| qwen3.6:35b-a3b | LS21 | window_fts5 | 5,307 → 4,101 | 22.72% | F → P | 4/4 → 4/4 |
| qwen3.6:35b-a3b | LS22 | complete_documents | 3,613 → 3,718 | -2.91% | F → F | 3/3 → 2/3 |
| qwen3.6:35b-a3b | LS23 | window_fts5 | 4,921 → 3,876 | 21.24% | F → F | 3/3 → 2/3 |
| qwen3.6:35b-a3b | LS24 | window_fts5 | 4,933 → 4,035 | 18.20% | F → F | 4/4 → 2/4 |

## Frozen review and provenance

An independent human must assess all 96 hash-bound raw answers against the same frozen facts, constraints and sources. A second reviewer adjudicates disputes and the frozen 20-answer sample (LS01, LS05, LS08, LS16, LS23 across all arms/models). Keep model/condition/usage labels and the private key hidden until judgments are locked. Output style can still reveal clues. Unknown or disputed judgments remain unknown; do not alter the gold criteria or repair answers.

Execution freeze SHA-256: `0ab921ca03228a08b6c7445d902051e81dcd5f34e644fa82810f7447ca56f49d`. Original 96-answer packet SHA-256: `d49a2fb2d01a49ce7fc1193931d947d479a549d1b7a65a941b3e8f9ae1d9bccd`. The companion JSON contains all 96 sanitized arm records and 48 pair records, including raw-answer hashes, measured quality gates, coverage and unknown fields. Internal operational logs, private keys, account data and personal paths are excluded.

No additional model inference or semantic scoring was performed to prepare this report. Historical measurements remain immutable.
