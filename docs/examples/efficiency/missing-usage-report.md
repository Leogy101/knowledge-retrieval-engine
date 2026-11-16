# Paired efficiency report

Evidence: **synthetic**.
Synthetic verification only; no real workflow savings demonstrated.
Disabled model: fixture/fixture-model; requested reasoning fingerprint: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`.
Enabled model: fixture/fixture-model; requested reasoning fingerprint: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`.
actual_cost currency (disabled / enabled): USD / USD.
estimated_cost currency (disabled / enabled): USD / USD.

Controlled conditions: true. Quality preserved: true.
Arithmetic reductions below are not savings claims; qualified claims appear after the table.

| Metric | Disabled | Enabled | Change |
|---|---:|---:|---:|
| input_tokens | 300 | unknown | N/A |
| output_tokens | 40 | unknown | N/A |
| cache_read_tokens | 80 | unknown | N/A |
| cache_write_tokens | 20 | unknown | N/A |
| reasoning_tokens | 10 | unknown | N/A |
| total_tokens | 340 | unknown | N/A |
| uncached_input_tokens | 200 | unknown | N/A |
| provider_reported_total | 340 | unknown | N/A |
| model_requests | 2 | unknown | N/A |
| model_input_bytes | 2000 | unknown | N/A |
| injected_tool_bytes | 400 | unknown | N/A |
| injected_evidence_bytes | 200 | unknown | N/A |
| estimated_input_tokens | 500 | unknown | N/A |
| actual_cost | 0.004 | unknown | N/A |
| estimated_cost | 0.006 | unknown | N/A |
| tool_calls | 1 | 2 | -100% reduction (regression) |
| tool_response_bytes | 200 | 260 | -30% reduction (regression) |
| tool_elapsed_seconds | 0.1 | 0.2 | -100% reduction (regression) |
| completion_seconds | 2 | 2.5 | -25% reduction (regression) |
| retrieval_core_seconds | 0.01 | 0.02 | -100% reduction (regression) |
| retrieval_round_trip_seconds | 0.1 | 0.15 | -50% reduction (regression) |
| validation_seconds | 0 | 0.05 | N/A (regression) |
| routing_seconds | 0 | 0 | N/A |
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
Coverage (disabled / enabled): total_tokens=complete / partial; actual_cost=complete / partial; estimated_cost=complete / partial; completion_seconds=complete / complete.
Context bytes, estimated tokens, billed charges and estimated costs are separate measures.
All observed attempts are retained; unknown coverage blocks whole-workflow claims.
