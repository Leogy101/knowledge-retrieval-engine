# Security boundaries

The host supplying constructor grants is trusted. KRE does not authenticate
remote users, sandbox Python code, or protect the database from its OS owner.
Use separate databases for separate trust domains.

File ingestion requires explicit roots, rejects descendant symlinks and special
files, reads bounded UTF-8 input, and never executes document contents. Root
ancestors remain trusted. Document text cannot grant authority, access, egress
or tools. The host owns model/network execution.

Revocation/deletion excludes later retrieval/inspection but does not erase prior
copies or backups. Pre-use validation is not atomic provider-send cancellation.

Policy updates and task checkpoints are trusted host operations. A task entry
declaring any unavailable dependency is suppressed on resume, including its text;
standalone user assertions remain labeled assertions. KRE cannot discover
undeclared dependencies or decide whether arbitrary assertion text is true.
Required evidence fails with empty context if unavailable or over budget. Policy
updates invalidate old context snapshots but do not recall previously returned
material. Task cards and retained source snapshots contain local document text.

Report issues privately to the maintainer through an available private channel.
No public repository/security-reporting service exists yet. Provide synthetic
reproductions, not credentials or private documents.
