# Meridian envelope admission contract

Synthetic Meridian/Harbor evaluation document. No real organization, secret or person is represented.

A relay admits an envelope only when the compressed payload is at most 256 KiB and the declared schema is telemetry.v3. The limit applies before decompression.

The idempotency key is the pair (station_id, event_id). A duplicate with identical bytes returns the original receipt; a duplicate with different bytes is quarantined.

An HTTP 202 receipt means the envelope is durably queued, not that the observation has been published.

The mobile uploader and the station relay share this contract. A browser refresh must not mint a replacement event identifier.

