# Meridian batch-client configuration

Synthetic Meridian/Harbor evaluation document. No real organization, secret or person is represented.

```json
{"batch": {"max_envelopes": 12, "flush_ms": 750}, "retry": {"additional_attempts": 0}, "ordering": "station_then_event"}
```

flush_ms is an integer number of milliseconds. additional_attempts excludes the first transmission. station_then_event orders first by station_id and then by event_id; it does not reorder by arrival time.

This configuration is the satellite training-client example. Invalid configuration is rejected rather than silently clamped.

