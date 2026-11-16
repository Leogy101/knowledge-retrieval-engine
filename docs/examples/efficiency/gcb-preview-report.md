# Paired efficiency report

Evidence: **synthetic**.
Synthetic verification only; no real workflow savings demonstrated.
Disabled model: fixture/fixture-model; requested reasoning fingerprint: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`.
Enabled model: fixture/fictional-candidate; requested reasoning fingerprint: `1d714e98c38bb71fb4888e3737689a23f7f1921056191f1ce6de34ab3578e064`.
actual_cost currency (disabled / enabled): USD / USD.
estimated_cost currency (disabled / enabled): USD / USD.

Controlled conditions: true. Quality preserved: true.
Arithmetic reductions below are not savings claims; qualified claims appear after the table.

| Metric | Disabled | Enabled | Change |
|---|---:|---:|---:|
| input_tokens | 300 | 160 | 46.666667% reduction |
| output_tokens | 40 | 40 | 0% reduction |
| cache_read_tokens | 80 | 40 | 50% reduction |
| cache_write_tokens | 20 | 0 | 100% reduction |
| reasoning_tokens | 10 | 10 | 0% reduction |
| total_tokens | 340 | 200 | 41.176471% reduction |
| uncached_input_tokens | 200 | 120 | 40% reduction |
| provider_reported_total | 340 | 200 | 41.176471% reduction |
| model_requests | 2 | 2 | 0% reduction |
| model_input_bytes | 2000 | 1400 | 30% reduction |
| injected_tool_bytes | 400 | 400 | 0% reduction |
| injected_evidence_bytes | 200 | 200 | 0% reduction |
| estimated_input_tokens | 500 | 350 | 30% reduction |
| actual_cost | 0.004 | 0.003 | 25% reduction |
| estimated_cost | 0.006 | 0.004 | 33.333333% reduction |
| tool_calls | 1 | 2 | -100% reduction (regression) |
| tool_response_bytes | 200 | 260 | -30% reduction (regression) |
| tool_elapsed_seconds | 0.1 | 0.2 | -100% reduction (regression) |
| completion_seconds | 2 | 2.5 | -25% reduction (regression) |
| retrieval_core_seconds | 0.01 | 0.02 | -100% reduction (regression) |
| retrieval_round_trip_seconds | 0.1 | 0.15 | -50% reduction (regression) |
| validation_seconds | 0 | 0.05 | N/A (regression) |
| routing_seconds | 0 | 0.001 | N/A (regression) |
| local_cpu_seconds | 0.02 | 0.04 | -100% reduction (regression) |
| setup_seconds | 0.3 | 0.3 | 0% reduction |
| setup_cpu_seconds | 0.1 | 0.1 | 0% reduction |
| storage_bytes | 4096 | 4096 | 0% reduction |
| quality_pass | 1 | 1 | 0 pp |
| citation_exactness | 1 | 1 | 0 pp |
| citation_support | 1 | 1 | 0 pp |
| evidence_recall | 1 | 1 | 0 pp |
| evidence_validity | 1 | 1 | 0 pp |

Qualified claims: total_tokens=synthetic_only; actual_cost=synthetic_only; estimated_cost=synthetic_only; completion_seconds=synthetic_only.
Coverage (disabled / enabled): total_tokens=complete / complete; actual_cost=complete / complete; estimated_cost=complete / complete; completion_seconds=complete / complete.
Context bytes, estimated tokens, billed charges and estimated costs are separate measures.
All observed attempts are retained; unknown coverage blocks whole-workflow claims.
