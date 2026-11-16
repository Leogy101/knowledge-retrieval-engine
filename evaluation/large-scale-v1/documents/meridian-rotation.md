# Meridian key rotation runbook

Synthetic Meridian/Harbor evaluation document. No real organization, secret or person is represented.

Before rotating a station signing key, register its new public key with the registry steward and retain the old verifier for forty-eight hours.

The station switches signing only after the registry returns the new key fingerprint. No shared secret is copied into the rotation ticket.

The overlap is measured from registry acknowledgement, not from when the operator drafted the ticket.

