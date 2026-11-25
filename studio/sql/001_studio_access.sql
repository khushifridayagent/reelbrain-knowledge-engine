-- OPTIONAL DEPLOYMENT STEP, NOT APPLIED TO PRODUCTION.
-- Run as the database administrator in the existing ReelBrain project ONLY.
-- Add isolated RPC facade + dedicated login. No ALTER/UPDATE/DELETE of core objects.
-- The role starts WITHOUT a password. Set it through psql \password reelbrain_studio_app
-- via a secure administrative connection, not a chat, migration file, or shell history.
begin;
create schema if not exists reelbrain_studio;
revoke all on schema reelbrain_studio from public, anon, authenticated;
do $role$ begin
 if not exists(select 1 from pg_catalog.pg_roles where rolname='reelbrain_studio_app') then
   create role reelbrain_studio_app login nosuperuser nocreatedb nocreaterole noinherit noreplication nobypassrls connection limit 3;
 end if;
end $role$;
grant usage on schema reelbrain_studio to reelbrain_studio_app;

create or replace function reelbrain_studio.sources(after_url text, page_size integer)
returns table(source_url text,creator text,published date,saved date,stage text,version timestamptz,caption text,speech text,research text)
language sql stable security definer set search_path='' as $f$
 select j.source_url,k.creator_handle,k.published_on,(j.created_at at time zone 'Asia/Kolkata')::date,
 coalesce(k.processing_stage,'media_pending'),greatest(j.updated_at,k.updated_at,r.updated_at),k.caption,
 k.verified_reel_content->'provider_audio_transcript'->>'text',k.external_topic_research::text
 from public.reelbrain_dm_jobs j left join public.reelbrain_reel_knowledge k using(source_url)
 left join reelbrain_research.reel_sources r on r.canonical_url=j.source_url
 where j.source_url>coalesce(after_url,'') and j.source_url ~ '^https://www[.]instagram[.]com/(reel|p|tv)/[A-Za-z0-9_-]{4,160}/$'
 order by j.source_url limit least(greatest(coalesce(page_size,100),1),100)
$f$;

create or replace function reelbrain_studio.evidence(selected_url text, after_id text,page_size integer)
returns table(evidence_id text,kind text,locator text,body text)
language sql stable security definer set search_path='' as $f$
 with items as (
  select 'obs:'||o.observation_id as eid,o.evidence_kind as ek,o.locator as loc,o.verbatim as txt
  from reelbrain_research.reel_observations o where o.source_url=selected_url
  union all
  select 'res:'||md5(r.canonical_resource_url||'|'||r.observation_id), 'resource:'||coalesce(r.verification_level,'unverified'),coalesce(o.locator,'resource'),
         concat_ws(E'\n',r.resource_name,r.canonical_resource_url,r.claimed_purpose)
  from reelbrain_research.reel_resources r left join reelbrain_research.reel_observations o on o.source_url=r.source_url and o.observation_id=r.observation_id where r.source_url=selected_url
  union all
  select 'speech:'||lpad(s.n::text,10,'0'),'third_party_speech_segment',concat('hosted-asr:',s.part->>'start','–',s.part->>'end','s'),s.part->>'text'
  from public.reelbrain_reel_knowledge k cross join lateral jsonb_array_elements(case when jsonb_typeof(k.verified_reel_content->'provider_audio_transcript'->'segments')='array' then k.verified_reel_content->'provider_audio_transcript'->'segments' else '[]'::jsonb end) with ordinality s(part,n)
  where k.source_url=selected_url and jsonb_typeof(s.part->'text')='string'
 ) select distinct on(eid) eid,ek,loc,txt from items where eid>coalesce(after_id,'') and length(trim(coalesce(txt,'')))>0
 order by eid,loc,txt limit least(greatest(coalesce(page_size,300),1),300)
$f$;

-- Restricted text-to-SQL substitute: fixed, parameterized count function, no generated SQL.
create or replace function reelbrain_studio.counts(filters jsonb default '{}'::jsonb)
returns table(total bigint,completed bigint,partial bigint,media_pending bigint,queued bigint,active bigint,dead_letter bigint,reels bigint,posts bigint)
language sql stable security definer set search_path='' as $f$
 select count(*),count(*) filter(where j.status='processed' and k.processing_stage='completed'),
 count(*) filter(where k.processing_stage='partial_media'),count(*) filter(where k.processing_stage='media_pending' or k.processing_stage is null),
 count(*) filter(where j.status='queued'),count(*) filter(where j.status='leased'),count(*) filter(where j.status='dead_letter'),
 count(*) filter(where j.source_url like '%/reel/%' or j.source_url like '%/tv/%'),count(*) filter(where j.source_url like '%/p/%')
 from public.reelbrain_dm_jobs j left join public.reelbrain_reel_knowledge k using(source_url)
 where (coalesce(filters->>'creator','')='' or lower(k.creator_handle)=lower(filters->>'creator'))
 and (nullif(filters->>'date_from','') is null or (j.created_at at time zone 'Asia/Kolkata')::date >= (filters->>'date_from')::date)
 and (nullif(filters->>'date_to','') is null or (j.created_at at time zone 'Asia/Kolkata')::date <= (filters->>'date_to')::date)
 and (nullif(filters->>'published_from','') is null or k.published_on >= (filters->>'published_from')::date)
 and (nullif(filters->>'published_to','') is null or k.published_on <= (filters->>'published_to')::date)
 and (coalesce(filters->>'status','')='' or coalesce(k.processing_stage,'media_pending')=filters->>'status')
 and (coalesce(filters->>'tool','')='' or strpos(lower(coalesce(k.caption,'')||' '||coalesce(k.verified_reel_content->'provider_audio_transcript'->>'text','')),lower(filters->>'tool'))>0 or exists(select 1 from reelbrain_research.reel_observations o where o.source_url=j.source_url and strpos(lower(o.verbatim),lower(filters->>'tool'))>0) or exists(select 1 from reelbrain_research.reel_resources r where r.source_url=j.source_url and strpos(lower(concat_ws(' ',r.resource_name,r.canonical_resource_url,r.claimed_purpose)),lower(filters->>'tool'))>0))
$f$;

-- Owner-authenticated Studio submission: a new URL can only be appended to the existing
-- durable queue. No fake Instagram sender/receipt. Never re-open a completed job.
create or replace function reelbrain_studio.submit_url(input_url text)
returns table(job_id bigint,source_url text,status text,inserted boolean)
language plpgsql security definer set search_path='' as $f$
declare created_id bigint;
begin
 if input_url is null or input_url !~ '^https://www[.]instagram[.]com/(reel|p|tv)/[A-Za-z0-9_-]{4,160}/$' then raise exception 'Invalid canonical Instagram URL'; end if;
 insert into public.reelbrain_dm_jobs(source_url,inbound_event_id,sender_digest)
 values(input_url,encode(extensions.digest('studio-manual:'||input_url,'sha256'),'hex'),encode(extensions.digest('reelbrain-studio-manual-owner','sha256'),'hex'))
 on conflict on constraint reelbrain_dm_jobs_source_url_key do nothing returning id into created_id;
 return query select j.id,j.source_url,j.status,created_id is not null from public.reelbrain_dm_jobs j where j.source_url=input_url;
end $f$;
revoke all on all functions in schema reelbrain_studio from public,anon,authenticated;
grant execute on function reelbrain_studio.sources(text,integer),reelbrain_studio.evidence(text,text,integer),reelbrain_studio.counts(jsonb),reelbrain_studio.submit_url(text) to reelbrain_studio_app;
commit;
-- Audit before connecting: dedicated role should have no table privileges or unexpected PUBLIC grants.
-- select table_schema,table_name,privilege_type from information_schema.role_table_grants where grantee='reelbrain_studio_app';
-- select has_function_privilege('anon','reelbrain_studio.submit_url(text)','execute'); -- false
-- select has_function_privilege('reelbrain_studio_app','reelbrain_studio.submit_url(text)','execute'); -- true
