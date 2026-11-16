# Meridian Telemetry schema migration notes

Synthetic Meridian/Harbor evaluation document. No real organization, secret or person is represented.

telemetry.v2 used a single timestamp field. telemetry.v3 distinguishes event time from admission time. A migration preserves both when the original event time is known.

Do not manufacture an event time from a later import timestamp.

When an operation stops midway, retain the last completed checkpoint and mark the unfinished step. Do not infer completion from the absence of an alarm. The next operator revalidates the checkpoint before resuming.

Keep ordinary operational notes separate from source-derived assertions. A conclusion should cite the observation that supports it; uncertainty should remain visible when the observation is incomplete or stale.

Record the start and end of the observation window, including gaps. Report an unavailable reading as unavailable rather than as zero. The acceptance record names the actual measurement method and its limits.

