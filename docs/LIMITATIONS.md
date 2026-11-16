# Experimental-alpha limitations

KRE is a local, deterministic retrieval system with provenance and lifecycle
controls. It is not a universal memory system or an answer-generation service.

- Lexical matching can miss paraphrases and relevant passages without shared query
  words. Finding a source does not guarantee finding all of its useful passages.
- Results are selected under bounded candidate, item and byte limits. Ranking and
  packing are not globally optimal. Larger context alone is not a quality gain.
- `coverage: unknown` is deliberate. Without reference answers or explicit required
  references, KRE cannot automatically detect every missing fact. Packing
  diagnostics report only known omissions. Consumers must not infer completeness
  from `status: ok` or a high rank.
- Explicit required references prevent known evidence from silently disappearing;
  they cannot establish that the caller identified every necessary passage.
- Documents up to 1,200 normalized bytes are retained whole; larger documents use
  source-line/paragraph chunks. This can add surrounding text or lose retrieval
  coverage under tight budgets. Alpha evaluation must report both recall and bytes.
- Citations are exact source references. Exact quotation validation does not prove
  a generated claim is supported, correct or complete. Answer output validation is
  separate from retrieval. KRE performs no generative repair or model judging.
- Freshness and authority are declared metadata, not automatic truth, timestamp
  authority, conflict resolution or scheduled verification. Source policy reflects
  current trusted metadata, not an as-of policy history.
- Task continuity is extractive and dependency-based. It cannot discover undeclared
  dependencies in arbitrary assertions, or erase evidence already exported into an
  existing conversation.
- Local context estimates use UTF-8 bytes, not a provider tokenizer. Whole-prompt
  context, actual token usage, retries and costs belong to model execution and
  measurement. General quality-preserving token/time/cost savings remain unproven.
- File support is UTF-8 text/Markdown only. There is no PDF/Office extraction, OCR,
  semantic index, mandatory embeddings or recursive workspace crawl.
- POSIX file-safety primitives are required. A platform-independent wheel does not
  establish Windows file-ingestion support.
- The database, application code, trusted root ancestors and host configuration
  are part of the trust boundary. Use separate databases across hostile trust
  domains; shared-index ranking statistics are not strong multi-tenant isolation.
- Logical deletion is not secure erasure. Retained snapshots, database journals,
  backups and exported contexts need their own retention handling.
- Optional MCP exposes fixed operator-bound authority; it does not prove the
  downstream model or an individual OpenClaw agent's identity.

The retained 96-call experiment remains an immutable historical measurement.
Independent human semantic review is incomplete, including all 96 answers.
Known 35B LS04/LS05 mechanical regressions remain failures. No release document
should convert later offline recall improvements into measured answer quality or
new model-token savings.
