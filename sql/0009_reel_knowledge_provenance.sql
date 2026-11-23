-- Replayable schema for publicly sourced Reel metadata and independently verified research.
-- Apply ONLY to the isolated Reelbrain Knowledge Supabase project.
-- This table does NOT imply that actual Reel video frames or audio were analyzed.
create table if not exists public.reelbrain_reel_knowledge (
  source_url text primary key references public.reelbrain_dm_jobs(source_url) on delete cascade,
  creator_handle text,
  creator_display_name text,
  caption text,
  published_on date,
  source_provider text not null,
  metadata_observed_at timestamptz not null default now(),
  engagement_snapshot jsonb not null default '{}'::jsonb,
  verified_reel_content jsonb not null default '{}'::jsonb,
  external_topic_research jsonb not null default '{}'::jsonb,
  content_evidence jsonb not null default '[]'::jsonb,
  video_analyzed boolean not null default false,
  audio_transcribed boolean not null default false,
  ocr_analyzed boolean not null default false,
  processing_stage text not null default 'metadata_only' check
    (processing_stage in ('metadata_only','media_pending','partial_media','completed','blocked','needs_review')),
  updated_at timestamptz not null default now()
);
create index if not exists reelbrain_reel_knowledge_stage_idx
 on public.reelbrain_reel_knowledge(processing_stage);
alter table public.reelbrain_reel_knowledge enable row level security;
revoke all on public.reelbrain_reel_knowledge from public, anon, authenticated;
grant select,insert,update on public.reelbrain_reel_knowledge to service_role;
