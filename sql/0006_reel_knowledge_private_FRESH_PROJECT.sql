-- Only new Supabase Reelbrain Knowledge project; never run in another project.
create table if not exists reelbrain_research.reel_sources (
 canonical_url text primary key,
 local_source_id text not null,
 status text not null check(status in ('partial','evidence_saved','verified')),
 media_sha256 text,
 completeness text not null default 'NOT_AUDITED',
 stage_timings jsonb not null default '{}'::jsonb,
 stage_errors jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists reelbrain_research.reel_observations (
 source_url text not null references reelbrain_research.reel_sources(canonical_url),
 observation_id text not null,
 evidence_kind text not null,
 locator text not null,
 verbatim text not null,
 primary key(source_url,observation_id)
);
create table if not exists reelbrain_research.reel_resources (
 source_url text not null references reelbrain_research.reel_sources(canonical_url),
 canonical_resource_url text not null,
 resource_name text not null,
 claimed_purpose text not null,
 observation_id text not null,
 verification_level text not null default 'seen' check(verification_level in ('seen','exists','readme_checked','sandbox_tested','user_confirmed')),
 primary key(source_url,canonical_resource_url,observation_id),
 foreign key(source_url,observation_id) references reelbrain_research.reel_observations(source_url,observation_id)
);
create index if not exists reelbrain_reel_resource_lookup on reelbrain_research.reel_resources(canonical_resource_url);
create index if not exists reelbrain_reel_keyword_index on reelbrain_research.reel_resources
 using gin(to_tsvector('simple'::regconfig,coalesce(resource_name,'')||' '||coalesce(claimed_purpose,'')||' '||coalesce(canonical_resource_url,'')));
create index if not exists reelbrain_reel_observation_source on reelbrain_research.reel_observations(source_url,evidence_kind);
alter table reelbrain_research.reel_sources enable row level security;
alter table reelbrain_research.reel_observations enable row level security;
alter table reelbrain_research.reel_resources enable row level security;
revoke all on reelbrain_research.reel_sources,reelbrain_research.reel_observations,reelbrain_research.reel_resources from public,anon,authenticated;

create or replace function reelbrain_research.search_reels(query_text text,max_results integer default 15)
returns table(repo text,repo_url text,what_it_does text,core_features text,practical_use_cases text,verification_level text,source_locator text,search_rank real)
language sql stable security invoker set search_path=''
as $$
 select r.resource_name,r.canonical_resource_url,r.claimed_purpose,
        'Source-observed resource; independent features not verified'::text,
        'See source Reel and evidence before using'::text,
        r.verification_level,
        r.source_url||' @ '||o.locator,
        ts_rank_cd(to_tsvector('simple'::regconfig,coalesce(r.resource_name,'')||' '||coalesce(r.claimed_purpose,'')||' '||coalesce(r.canonical_resource_url,'')),
                   websearch_to_tsquery('simple'::regconfig,left(query_text,180)))::real
 from reelbrain_research.reel_resources r
 join reelbrain_research.reel_observations o on o.source_url=r.source_url and o.observation_id=r.observation_id
 where length(trim(coalesce(query_text,'')))>0 and
  to_tsvector('simple'::regconfig,coalesce(r.resource_name,'')||' '||coalesce(r.claimed_purpose,'')||' '||coalesce(r.canonical_resource_url,''))
  @@ websearch_to_tsquery('simple'::regconfig,left(query_text,180))
 order by 8 desc limit least(greatest(coalesce(max_results,15),1),50);
$$;
revoke all on function reelbrain_research.search_reels(text,integer) from public,anon,authenticated;
