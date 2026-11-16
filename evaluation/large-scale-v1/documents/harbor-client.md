# Harbor HTTP client contract

Synthetic Meridian/Harbor evaluation document. No real organization, secret or person is represented.

```json
{"timeout_ms": 2500, "retry": {"attempts": 0}, "headers": {"X-Training": "true"}}
```

timeout_ms is an integer in milliseconds. retry.attempts counts additional attempts, not the initial request. X-Training is the literal string "true", not a JSON boolean.

The example contains no authentication credential. A caller must not add an undocumented retry.

