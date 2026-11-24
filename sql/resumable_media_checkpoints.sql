-- Additive private stage evidence cache. No raw video bytes.
create table if not exists reelbrain_research.media_stage_checkpoints (
 source_url text not null,
 media_sha256 text not null check (media_sha256 ~ '^[0-9a-f]{64}$'),
 pipeline_version text not null,
 stage text not null check (stage in ('ocr','asr','vlm')),
 observations jsonb not null check (jsonb_typeof(observations)='array'),
 elapsed_ms bigint not null check (elapsed_ms>=0),
 created_at timestamptz not null default now(),
 primary key (source_url,media_sha256,pipeline_version,stage)
);
alter table reelbrain_research.media_stage_checkpoints enable row level security;
revoke all on reelbrain_research.media_stage_checkpoints from public,anon,authenticated;
