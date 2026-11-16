# Harbor snapshot and rollback

Synthetic Meridian/Harbor evaluation document. No real organization, secret or person is represented.

Before deployment, the operator records the immutable snapshot identifier and its SHA-256 checksum in the release card.

After rollback, reconcile the order ledger against the snapshot and probe /ready twice, thirty seconds apart. Any mismatch keeps traffic closed.

Snapshot creation alone is not evidence that a restore has been tested.

