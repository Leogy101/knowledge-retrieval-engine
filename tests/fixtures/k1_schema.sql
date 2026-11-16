-- Exact schema initialization from committed K1 e89c09d6a40bfbabc080902ea78d7409c5ad18a7.

            BEGIN IMMEDIATE;
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sources(
                source_id TEXT PRIMARY KEY, collection TEXT NOT NULL,
                authority TEXT NOT NULL, origin TEXT NOT NULL, freshness TEXT NOT NULL,
                egress TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'active', display_uri TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS revisions(
                revision_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources,
                text TEXT NOT NULL, content_hash TEXT NOT NULL, recorded_at TEXT NOT NULL,
                lifecycle TEXT NOT NULL, original_hash TEXT NOT NULL, parser_version TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS chunks(
                id INTEGER PRIMARY KEY, revision_id TEXT NOT NULL REFERENCES revisions,
                text TEXT NOT NULL, line_start INTEGER NOT NULL, line_end INTEGER NOT NULL);
            CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(text);
            CREATE TABLE IF NOT EXISTS tasks(
                task_id TEXT PRIMARY KEY, principal TEXT NOT NULL, scope_ref TEXT NOT NULL,
                refs_json TEXT NOT NULL);
            INSERT INTO metadata VALUES ('generation', '0');
            INSERT INTO metadata VALUES ('namespace', lower(hex(randomblob(16))));
            PRAGMA application_id=1263682865;
            PRAGMA user_version=1;
            COMMIT;
        