# Meridian disconnected station policy

Synthetic Meridian/Harbor evaluation document. No real organization, secret or person is represented.

A station may buffer observations locally for seventy-two hours. When it reconnects, it preserves the original event time and uploads in event_id order within each station.

Buffered observations older than seventy-two hours require curator review; the uploader must not relabel them as newly observed.

Offline buffering does not extend signing-key overlap or consent validity.

