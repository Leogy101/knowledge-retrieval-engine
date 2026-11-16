# Meridian Event clock reconciliation

Synthetic Meridian/Harbor evaluation document. No real organization, secret or person is represented.

Station event time, relay admission time and publication time are separate instants. A gap between them can describe buffering, review or delivery delay.

A reconciliation preserves each observed timestamp and records unknown clock offset rather than subtracting an invented correction.

The maintenance ledger preserves the prior entry and appends a correction with its rationale. It never overwrites the original evidence. A later correction is not automatically more authoritative without the required approval.

When an operation stops midway, retain the last completed checkpoint and mark the unfinished step. Do not infer completion from the absence of an alarm. The next operator revalidates the checkpoint before resuming.

Keep ordinary operational notes separate from source-derived assertions. A conclusion should cite the observation that supports it; uncertainty should remain visible when the observation is incomplete or stale.

