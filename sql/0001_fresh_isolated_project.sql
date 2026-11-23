-- Reelbrain v2 - FRESH SUPABASE PROJECT ONLY. DO NOT APPLY TO ANY EXISTING USER PROJECT.
-- No destructive changes: no DROP, TRUNCATE or data deletion.
-- Requires Supabase Postgres with pgvector extension available in extensions schema.
BEGIN;
CREATE SCHEMA IF NOT EXISTS reelbrain;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;
REVOKE ALL ON SCHEMA reelbrain FROM PUBLIC, anon, authenticated;

CREATE TABLE IF NOT EXISTS reelbrain.tenants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id uuid NOT NULL REFERENCES auth.users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(id,owner_id)
);
CREATE TABLE IF NOT EXISTS reelbrain.sources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES reelbrain.tenants(id),
  canonical_ref text NOT NULL,
  platform text NOT NULL CHECK(platform IN('instagram','document','local_media','youtube','github')),
  source_kind text NOT NULL,
  import_hash text NOT NULL,
  creator text,
  published_at timestamptz,
  ingested_at timestamptz NOT NULL DEFAULT now(),
  acquisition_status text NOT NULL DEFAULT 'awaiting_authorized_media',
  access_method text,
  rights_status text NOT NULL DEFAULT 'unknown',
  retention_expires timestamptz,
  UNIQUE(tenant_id, canonical_ref,import_hash),
  UNIQUE(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS reelbrain.assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  source_id uuid NOT NULL,
  storage_key text NOT NULL,
  sha256 text NOT NULL,
  mime_type text NOT NULL,
  byte_count bigint NOT NULL CHECK(byte_count>=0),
  captured_at timestamptz NOT NULL DEFAULT now(),
  retention_expires timestamptz,
  FOREIGN KEY(source_id,tenant_id) REFERENCES reelbrain.sources(id,tenant_id),
  UNIQUE(id,tenant_id), UNIQUE(tenant_id,sha256)
);
CREATE TABLE IF NOT EXISTS reelbrain.evidence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  source_id uuid NOT NULL,
  asset_id uuid,
  method text NOT NULL CHECK(method IN ('ocr','asr','caption','document','manual','verified_doc')),
  locator text NOT NULL,
  verbatim text NOT NULL,
  confidence numeric(5,4) CHECK(confidence IS NULL OR (confidence>=0 AND confidence<=1)),
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(source_id,tenant_id) REFERENCES reelbrain.sources(id,tenant_id),
  FOREIGN KEY(asset_id,tenant_id) REFERENCES reelbrain.assets(id,tenant_id),
  UNIQUE(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS reelbrain.resources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES reelbrain.tenants(id),
  canonical_url text NOT NULL,
  resource_name text NOT NULL,
  resource_type text,
  creator_claim text,
  verified_purpose text,
  installation_guide text,
  use_cases text[] NOT NULL DEFAULT '{}',
  topics text[] NOT NULL DEFAULT '{}',
  verification_level text NOT NULL DEFAULT 'seen'
    CHECK(verification_level IN('seen','exists','readme_checked','sandbox_run','user_confirmed','unresolved')),
  verification_receipt jsonb,
  flagged boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK(verification_level IN('seen','unresolved') OR verification_receipt IS NOT NULL),
  UNIQUE(tenant_id,canonical_url), UNIQUE(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS reelbrain.resource_evidence (
  tenant_id uuid NOT NULL,
  resource_id uuid NOT NULL,
  evidence_id uuid NOT NULL,
  relation text NOT NULL DEFAULT 'mentioned',
  PRIMARY KEY(tenant_id,resource_id,evidence_id),
  FOREIGN KEY(resource_id,tenant_id) REFERENCES reelbrain.resources(id,tenant_id),
  FOREIGN KEY(evidence_id,tenant_id) REFERENCES reelbrain.evidence(id,tenant_id)
);
CREATE TABLE IF NOT EXISTS reelbrain.knowledge_chunks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES reelbrain.tenants(id),
  source_id uuid NOT NULL,
  evidence_id uuid NOT NULL,
  chunk_text text NOT NULL,
  embedding extensions.vector(768),
  embedding_model text,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(source_id,tenant_id) REFERENCES reelbrain.sources(id,tenant_id),
  FOREIGN KEY(evidence_id,tenant_id) REFERENCES reelbrain.evidence(id,tenant_id),
  CHECK(embedding IS NULL OR embedding_model IS NOT NULL)
);
CREATE TABLE IF NOT EXISTS reelbrain.jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES reelbrain.tenants(id),
  idempotency_key text NOT NULL,
  kind text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  state text NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','running','partial','done','failed','cancelled')),
  attempts smallint NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 10),
  timings_ms jsonb NOT NULL DEFAULT '{}'::jsonb,
  error jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,kind,idempotency_key)
);
CREATE TABLE IF NOT EXISTS reelbrain.eval_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES reelbrain.tenants(id),
  dataset_version text NOT NULL,
  pipeline_version text NOT NULL,
  exact_url_precision numeric(5,4),
  exact_url_recall numeric(5,4),
  unsupported_url_count integer NOT NULL DEFAULT 0,
  sample_size integer NOT NULL DEFAULT 0,
  p50_latency_ms integer,
  p95_latency_ms integer,
  cost_usd numeric,
  passed boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK(NOT passed OR (sample_size>=20 AND exact_url_precision>=0.98 AND exact_url_recall>=0.95 AND unsupported_url_count=0))
);

-- Every table in this private schema is RLS-enabled as defense in depth.
ALTER TABLE reelbrain.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE reelbrain.sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE reelbrain.assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE reelbrain.evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE reelbrain.resources ENABLE ROW LEVEL SECURITY;
ALTER TABLE reelbrain.resource_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE reelbrain.knowledge_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE reelbrain.jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE reelbrain.eval_runs ENABLE ROW LEVEL SECURITY;
-- No policies for anon/authenticated. Only a deliberately scoped server worker
-- with a protected Postgres connection should operate on these tables.
-- When adding a public client API, design owner RLS policies first.

CREATE INDEX IF NOT EXISTS idx_sources_tenant ON reelbrain.sources(tenant_id,ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_source ON reelbrain.evidence(tenant_id,source_id);
CREATE INDEX IF NOT EXISTS idx_resources_tenant ON reelbrain.resources(tenant_id,canonical_url);
CREATE INDEX IF NOT EXISTS idx_resource_evidence ON reelbrain.resource_evidence(tenant_id,resource_id);
CREATE INDEX IF NOT EXISTS idx_chunks_fts ON reelbrain.knowledge_chunks USING gin(to_tsvector('english',chunk_text));
-- HNSW requires nonempty embeddings & sensible scale; defer to measured rollout.
CREATE INDEX IF NOT EXISTS idx_jobs_claim ON reelbrain.jobs(tenant_id,state,created_at);

-- Uses owner check to prevent a caller from searching another tenant. SECURITY INVOKER.
CREATE OR REPLACE FUNCTION reelbrain.hybrid_search(
  search_tenant uuid, search_text text, search_embedding extensions.vector(768), match_count integer DEFAULT 20
)
RETURNS TABLE(id uuid, source_id uuid, evidence_id uuid, chunk_text text, score double precision)
LANGUAGE sql STABLE SECURITY INVOKER AS $$
  WITH permitted AS (
    SELECT c.* FROM reelbrain.knowledge_chunks c
    JOIN reelbrain.tenants t ON c.tenant_id=t.id
    WHERE c.tenant_id=search_tenant AND t.owner_id=(SELECT auth.uid())
  ),
  fts AS (
    SELECT p.id, row_number() OVER(ORDER BY ts_rank_cd(to_tsvector('english', p.chunk_text), websearch_to_tsquery('english',search_text)) DESC) AS ix
    FROM permitted p
    WHERE to_tsvector('english',p.chunk_text) @@ websearch_to_tsquery('english',search_text)
    LIMIT 120
  ),
  vectors AS (
    SELECT p.id, row_number() OVER(ORDER BY p.embedding <=> search_embedding) AS ix
    FROM permitted p WHERE p.embedding IS NOT NULL AND search_embedding IS NOT NULL
    ORDER BY p.embedding <=> search_embedding LIMIT 120
  )
  SELECT p.id,p.source_id,p.evidence_id,p.chunk_text,
  (COALESCE(1.0/(60+fts.ix),0.0)+COALESCE(1.0/(60+vectors.ix),0.0))::double precision score
  FROM permitted p
  LEFT JOIN fts USING(id) LEFT JOIN vectors USING(id)
  WHERE fts.ix IS NOT NULL OR vectors.ix IS NOT NULL
  ORDER BY score DESC LIMIT LEAST(GREATEST(match_count,1),50)
$$;
REVOKE ALL ON FUNCTION reelbrain.hybrid_search(uuid,text,extensions.vector,integer) FROM PUBLIC;
COMMIT;
