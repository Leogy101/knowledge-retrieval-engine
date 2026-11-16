# Security and privacy

KRE is a local retrieval library and CLI. It does not run a model, contact a provider, execute document contents or start a network service. The optional MCP adapter uses standard input/output and inherits its host's trust boundary.

## Supported security boundary

The operator binds a principal, collection grants, permitted filesystem roots and allowed destinations. Requests cannot enlarge those grants. Use a separate database for each trust domain. KRE does not authenticate remote users, sandbox arbitrary Python or protect a database from its operating-system owner.

Local ingestion supports bounded UTF-8 `.txt`, `.md` and `.markdown` files. Descriptor-relative reads reject symlinks beneath a trusted root, special files and disallowed paths. The root and its ancestors must be controlled by the operator. This file-ingestion protection requires POSIX filesystem capabilities; Windows file ingestion is unsupported and fails explicitly rather than falling back to weaker checks.

Documents are untrusted evidence. Their text cannot grant access, change lifecycle or destination policy, or enable tools. KRE returns source identifiers, immutable revision references, source hashes and exact line citations. A relevant citation does not establish that a source is authoritative or that its claims are true.

## Data handling

The database retains source text, immutable revisions and task checkpoints. Protect the database, parent directory, backups and exported context with appropriate OS permissions. KRE creates new database files with restrictive permissions on supported POSIX systems; existing file permissions remain the operator's responsibility. KRE does not encrypt data at rest.

Revocation and deletion exclude affected material from subsequent authorized retrieval and inspection. They cannot recall previously returned context, model prompts, logs or backups. Context validation detects changes since retrieval, but is not an atomic network-send control. The host must validate immediately before use and enforce the destination policy on every external transmission.

Task resume revalidates declared evidence dependencies and suppresses entries whose dependencies are unavailable. Undeclared dependencies and unsupported assertions cannot always be detected. Required-evidence APIs return an explicit error when a supplied required reference is unavailable or cannot fit. Ordinary retrieval cannot prove that every fact needed for an answer was found.

The default MCP tool surface is read-only retrieval and validation. Source ingestion and policy changes remain local-owner operations. Optional checkpoint tools require an explicit trusted local-client binding. Do not expose the database or CLI as an unauthenticated remote service.

## Reporting a vulnerability

Do not put credentials, private documents, database files or exploit details in public issues. When private vulnerability reporting is enabled for this repository, use **Security → Report a vulnerability** at [Leogy101/knowledge-retrieval-engine](https://github.com/Leogy101/knowledge-retrieval-engine/security/advisories/new). Before publication or if that option is unavailable, request a private reporting channel from the maintainer without posting sensitive details. Do not send sensitive material until that channel has been confirmed.

Include the KRE version, OS/Python/SQLite versions, expected boundary, observed behavior and a minimal synthetic reproduction. Report incorrect access or destination enforcement, citation corruption, unsafe file reads and unintended disclosure as security concerns. Lexical retrieval misses are quality limitations unless they also violate a security boundary.

This experimental alpha has no promised security-support period. Security fixes will be identified in the changelog. The [publication procedure](docs/PUBLICATION_PLAN.md) requires enabling private vulnerability reporting after authorized repository creation and verifying both the setting and the report form before release. The presence of this policy does not imply that the repository has been published or those services are already enabled.
