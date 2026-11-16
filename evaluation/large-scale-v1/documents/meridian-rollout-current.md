# Meridian relay rollout revision 5

Synthetic Meridian/Harbor evaluation document. No real organization, secret or person is represented.

Revision 5 requires a shadow-ingest comparison for thirty minutes, then checksum reconciliation, then curator approval before public traffic is enabled.

A mismatch during shadow ingest requires rollback to the last approved build. Save the mismatch receipt identifiers; do not discard them to make the comparison pass.

Revision 5 explicitly replaces revision 4. The version number alone is not the authority: the signed release decision adopts this sequence.

Operators must preserve the observation identifiers while comparing builds.

