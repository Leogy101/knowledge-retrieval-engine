# Meridian configuration validation rules

Synthetic Meridian/Harbor evaluation document. No real organization, secret or person is represented.

Reject a batch configuration if max_envelopes is outside 1 through 12 inclusive, flush_ms is not a positive integer, or additional_attempts is not zero for this benchmark profile.

Validation is atomic: an invalid configuration leaves the prior effective configuration unchanged. A validation error is not a partially applied update.

All keys in the documented example are required. Unknown keys are rejected.

