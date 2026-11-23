-- Reelbrain: optional ADDITIVE migration after 0001 on NEW isolated project ONLY.
-- This file has not been run on Supabase: staging QA, auth and cost approval required.
-- Do not apply to GTA VI or any pre-existing database. No destructive operations.
BEGIN;
CREATE TABLE IF NOT EXISTS reelbrain.archive_payloads (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 tenant_id uuid NOT NULL REFERENCES reelbrain.tenants(id),
 source_id uuid NOT NULL,
 original_text text NOT NULL,
 content_sha256 char(64) NOT NULL CHECK(content_sha256 ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY (source_id,tenant_id) REFERENCES reelbrain.sources(id,tenant_id),
 UNIQUE (tenant_id,source_id)
);
CREATE TABLE IF NOT EXISTS reelbrain.reel_mentions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 tenant_id uuid NOT NULL REFERENCES reelbrain.tenants(id),
 conversation_source_id uuid NOT NULL,
 reel_source_id uuid NOT NULL,
 locator text NOT NULL,
 char_offset bigint NOT NULL CHECK(char_offset>=0),
 context_note text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY (conversation_source_id,tenant_id) REFERENCES reelbrain.sources(id,tenant_id),
 FOREIGN KEY (reel_source_id,tenant_id) REFERENCES reelbrain.sources(id,tenant_id),
 UNIQUE (tenant_id,conversation_source_id,reel_source_id,char_offset)
);
CREATE INDEX IF NOT EXISTS idx_reel_mentions_lookup
 ON reelbrain.reel_mentions (tenant_id,reel_source_id);
CREATE TABLE IF NOT EXISTS reelbrain.reel_processing (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 tenant_id uuid NOT NULL REFERENCES reelbrain.tenants(id),
 reel_source_id uuid NOT NULL,
 result_source_id uuid NOT NULL,
 media_sha256 char(64) NOT NULL CHECK(media_sha256 ~ '^[0-9a-f]{64}$'),
 state text NOT NULL CHECK(state IN('processed','partial')),
 processed_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY (reel_source_id,tenant_id) REFERENCES reelbrain.sources(id,tenant_id),
 FOREIGN KEY (result_source_id,tenant_id) REFERENCES reelbrain.sources(id,tenant_id),
 UNIQUE(tenant_id,reel_source_id,result_source_id,media_sha256)
);
CREATE INDEX IF NOT EXISTS idx_reel_processing_lookup
 ON reelbrain.reel_processing (tenant_id,reel_source_id,processed_at DESC);
ALTER TABLE reelbrain.archive_payloads ENABLE ROW LEVEL SECURITY;
ALTER TABLE reelbrain.reel_mentions ENABLE ROW LEVEL SECURITY;
ALTER TABLE reelbrain.reel_processing ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON reelbrain.archive_payloads FROM PUBLIC,anon,authenticated;
REVOKE ALL ON reelbrain.reel_mentions FROM PUBLIC,anon,authenticated;
REVOKE ALL ON reelbrain.reel_processing FROM PUBLIC,anon,authenticated;
-- No broad policies, direct role grants or PUBLIC API endpoints are created.
COMMIT;
