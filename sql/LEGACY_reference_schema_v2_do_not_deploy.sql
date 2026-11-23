-- Reel Knowledge Agent: schema v2 (Postgres 16 + pgvector + pg_trgm). Works on Supabase.
-- EMBEDDING DIMENSION: 768 below. It must equal the output_dimensionality you request from the embedding model.
-- Confirm what your chosen Gemini embedding model supports, then search-and-replace 768 (3 places).
-- Single-user by default (tenant_id has a constant default). For multi-user: ENABLE ROW LEVEL SECURITY per table
-- and add policies on tenant_id; never ship a service-role key to a client.
create extension if not exists pgcrypto;
create extension if not exists vector;
create extension if not exists pg_trgm;

create table sources (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null default '00000000-0000-0000-0000-000000000001',
  platform         text not null default 'instagram',
  canonical_url    text not null,
  shortcode        text,
  kind             text not null check (kind in ('reel','carousel','video','article','repo','pdf')),
  creator          text,
  caption          text,
  duration_sec     numeric,
  status           text not null default 'queued'
                   check (status in ('queued','acquiring','metadata_saved','partial','verified','failed','unavailable')),
  error_code       text,
  acquired_via     text check (acquired_via in ('own_ip_ytdlp','apify','browser','upload')),
  content_sha256   text,
  pipeline_version text,
  created_at       timestamptz not null default now(),
  unique (tenant_id, canonical_url)
);

create table assets (
  id          uuid primary key default gen_random_uuid(),
  source_id   uuid not null references sources(id) on delete cascade,
  kind        text not null check (kind in ('video','audio','image','frame','transcript')),
  storage_key text,
  sha256      text,
  mime        text,
  slide_index int,
  t_ms        bigint,
  phash       bit(256),
  expires_at  timestamptz,           -- raw media gets a short retention; derived evidence stays
  created_at  timestamptz not null default now()
);

create table evidence (
  id               uuid primary key default gen_random_uuid(),
  source_id        uuid not null references sources(id) on delete cascade,
  asset_id         uuid references assets(id) on delete set null,
  modality         text not null check (modality in ('on_screen','speech','caption','slide','metadata')),
  slide_index      int,
  t_start_ms       bigint,
  t_end_ms         bigint,
  verbatim         text not null,
  method           text not null check (method in ('gemini','asr_grok','asr_sarvam','tesseract','caption','human')),
  confidence       real check (confidence between 0 and 1),
  pipeline_version text not null,
  created_at       timestamptz not null default now()
);
create index evidence_source_t on evidence (source_id, t_start_ms);

create table resources (
  id                  uuid primary key default gen_random_uuid(),
  tenant_id           uuid not null default '00000000-0000-0000-0000-000000000001',
  source_id           uuid not null references sources(id) on delete cascade,
  primary_evidence_id uuid not null references evidence(id),
  name                text not null,
  kind                text not null check (kind in ('github_repo','npm_package','pypi_package','website','command','tool_name','course','other')),
  observed            text not null,                       -- exactly what the Reel showed
  canonical           text,                                -- owner/repo or package, only once resolved
  claimed_purpose     text,                                -- the creator's claim, never presented as fact
  evidence_level      text not null default 'seen'
                      check (evidence_level in ('seen','exists','readme_checked','sandbox_run','user_confirmed')),
  verification_status text not null default 'pending'
                      check (verification_status in ('pending','verified','repaired_verified','resolved_by_search','ambiguous','not_found','rate_limited','error')),
  flags               text[] not null default '{}',
  health              jsonb not null default '{}',         -- stars, license, pushed_at, created_at ...
  verified_at         timestamptz,
  created_at          timestamptz not null default now(),
  -- no fabricated trust: anything above 'seen' needs a successful verification behind it
  constraint level_needs_verification check (
    evidence_level = 'seen' or verification_status in ('verified','repaired_verified','resolved_by_search'))
);
create unique index resources_dedupe on resources (source_id, kind, lower(name));
create index resources_canonical on resources (lower(canonical));

create table promises (        -- "comment REPOS for the links": recorded, never fabricated
  id          uuid primary key default gen_random_uuid(),
  source_id   uuid not null references sources(id) on delete cascade,
  evidence_id uuid not null references evidence(id),
  what        text not null,
  mechanism   text not null check (mechanism in ('comment_keyword','dm','link_in_bio','other')),
  keyword     text,
  status      text not null default 'unresolved' check (status in ('unresolved','resolved_by_user'))
);

create table chunks (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null default '00000000-0000-0000-0000-000000000001',
  source_id   uuid not null references sources(id) on delete cascade,
  resource_id uuid references resources(id) on delete cascade,
  evidence_id uuid references evidence(id) on delete set null,
  content     text not null,                    -- include name + canonical + verbatim so exact queries hit
  embedding   vector(768),
  fts         tsvector generated always as (to_tsvector('simple', content)) stored,
  created_at  timestamptz not null default now()
);
create index chunks_fts  on chunks using gin (fts);
create index chunks_trgm on chunks using gin (content gin_trgm_ops);
create index chunks_vec  on chunks using hnsw (embedding vector_cosine_ops);

create table jobs (
  id              uuid primary key default gen_random_uuid(),
  source_id       uuid references sources(id) on delete cascade,
  stage           text not null,
  state           text not null default 'queued' check (state in ('queued','running','done','failed','dead')),
  priority        smallint not null default 5,
  attempts        int not null default 0,
  max_attempts    int not null default 3,
  run_after       timestamptz not null default now(),
  locked_at       timestamptz,
  idempotency_key text not null unique,
  error_code      text,
  timings_ms      jsonb not null default '{}',    -- t_access, t_gemini, t_asr, t_frames, t_verify, t_total
  created_at      timestamptz not null default now(),
  finished_at     timestamptz
);
create index jobs_ready on jobs (stage, priority, run_after) where state = 'queued';

-- worker pull: one job per call, no two workers ever get the same row
create or replace function claim_job(p_stage text) returns jobs language sql as $$
  update jobs set state = 'running', locked_at = now(), attempts = attempts + 1
  where id = (select id from jobs
              where state = 'queued' and stage = p_stage and run_after <= now()
              order by priority, run_after
              for update skip locked limit 1)
  returning *;
$$;

create table projects (
  id        uuid primary key default gen_random_uuid(),
  tenant_id uuid not null default '00000000-0000-0000-0000-000000000001',
  name      text not null,
  notes     text,
  unique (tenant_id, name)
);
create table project_resources (
  project_id   uuid not null references projects(id) on delete cascade,
  resource_id  uuid not null references resources(id) on delete cascade,
  why_relevant text,
  primary key (project_id, resource_id)
);
create table feedback (
  id          uuid primary key default gen_random_uuid(),
  resource_id uuid references resources(id) on delete cascade,
  kind        text not null check (kind in ('wrong_url','merge','dead_link','confirmed_works','not_useful')),
  note        text,
  created_at  timestamptz not null default now()
);
create table eval_runs (
  id               uuid primary key default gen_random_uuid(),
  pipeline_version text not null,
  golden_set       text not null,
  metrics          jsonb not null,           -- url_precision, url_recall, unsupported_urls, wer, p50_ms, p95_ms, cost_usd
  created_at       timestamptz not null default now()
);

-- Hybrid retrieval: exact substring + full-text + vector, fused with Reciprocal Rank Fusion.
-- q_emb may be null (exact + full-text only). Exact lane is what makes "onyx-dot-app/onyx" work every time.
create or replace function hybrid_search(q text, q_emb vector(768) default null, k int default 10, rrf_k int default 60)
returns table (chunk_id uuid, source_id uuid, resource_id uuid, content text, score double precision, lanes text[])
language sql stable as $$
  with
  exact as (
    select c.id, row_number() over (order by length(c.content)) as rnk
    from chunks c
    where c.content ilike '%' || regexp_replace(q, '([\\%_])', '\\\1', 'g') || '%'
    limit 50
  ),
  ft as (
    select c.id, row_number() over (order by ts_rank_cd(c.fts, tq) desc) as rnk
    from chunks c, websearch_to_tsquery('simple', q) tq
    where c.fts @@ tq
    limit 50
  ),
  vec as (
    select id, row_number() over (order by d) as rnk
    from (select c.id, c.embedding <=> q_emb as d from chunks c
          where q_emb is not null and c.embedding is not null order by d limit 50) s
  ),
  fused as (
    select id, sum(1.0 / (rrf_k + rnk)) as score, array_agg(lane order by lane) as lanes
    from (select id, rnk, 'exact' as lane from exact
          union all select id, rnk, 'fulltext' from ft
          union all select id, rnk, 'vector' from vec) u
    group by id
  )
  select c.id, c.source_id, c.resource_id, c.content, f.score, f.lanes
  from fused f join chunks c on c.id = f.id
  order by f.score desc
  limit k;
$$;
