# Public test and fixture scope

The public source candidate preserves **304 of the 306 original test methods**, before counting any new alpha tests. All deterministic output-validation, access-control, lifecycle, context-budget, filesystem, authorization and fake-transport tests remain. Full POSIX test discovery includes the historical benchmark runner's fake-transport guards; it performs no live model inference.

Two methods remain private because they exercise captured private-calibration payload archives:

- `test_retained_fixture_hashes_and_frozen_assertion_oracle`
- `test_retained_outputs_preserve_observed_component_failures`

They remain unchanged in the original private repository and run in its full regression suite. They are not marked skipped to conceal a failing public check. All 20 synthetic deterministic tests in the same output-validation module remain public, including malformed JSON, fenced JSON, exact quotes, incorrect citation spans, unsupported frozen assertions, missing required evidence and privacy-negative tests. The exclusion changes public test inventory, not the benchmark's historical scores.

The public calibration reproduction uses a clearly labeled synthetic derivative of three documentation fixtures. Neutral equal-length labels replace private agent names; required source-management passages, line coordinates, byte lengths, task query, budgets and assertions remain unchanged. Its source hash is explicitly different from the retained private original. This derivative is not a record of a new model run.

The historical fragmented-gold fixture is an exact projection of only the accepted variant's existing gold fields. It omits unnecessary context bodies, alternative variants and timing data; labels and coordinates are unchanged. The generic host-attribution fixture replaces a private-agent provenance field name with a generic host label. Its measurements, unknown values and assertions are unchanged.

`tests/fixtures/public-derivatives.json` records source and public SHA-256 hashes and each transformation. The original source documents, benchmark evidence, frozen scoring and private Git history remain unchanged. Frozen large-suite tasks, documents, protocol and hashes are included as applicable to the offline tests; their retained execution files do not authorize a new live run.

The optional public-source OpenClaw replay requires a separately supplied matching public package and Node. It is skipped when that package is absent, as before; the core package does not require either dependency. Its recorded fake-transport evidence is tested without accessing a live installation.

Windows CI covers only a named portable-core subset. POSIX descriptor-relative file ingestion and its dependent CLI demonstration are deliberately unsupported on Windows. A passing Windows-core job must not be described as Windows file-ingestion support.
