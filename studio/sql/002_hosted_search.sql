-- Bounded source cards over the same private evidence used by the offline index.
create or replace function reelbrain_studio.hosted_search(
    words text[], filters jsonb, selected text[], page_offset integer, page_limit integer
) returns table(card jsonb, total bigint)
language sql stable security definer set search_path='' as $$
with corpus as materialized (
    select j.source_url, k.creator_handle creator, k.published_on published,
           (j.created_at at time zone 'Asia/Kolkata')::date saved,
           coalesce(k.processing_stage,'media_pending') status, k.caption,
           k.verified_reel_content->'provider_audio_transcript' transcript,
           k.external_topic_research research
    from public.reelbrain_dm_jobs j left join public.reelbrain_reel_knowledge k using(source_url)
    where (selected is null or j.source_url=any(selected))
      and (filters->>'creator' is null or lower(k.creator_handle)=lower(filters->>'creator'))
      and (filters->>'status' is null or coalesce(k.processing_stage,'media_pending')=filters->>'status')
      and (filters->>'date_from' is null or (j.created_at at time zone 'Asia/Kolkata')::date >= (filters->>'date_from')::date)
      and (filters->>'date_to' is null or (j.created_at at time zone 'Asia/Kolkata')::date <= (filters->>'date_to')::date)
      and (filters->>'published_from' is null or k.published_on >= (filters->>'published_from')::date)
      and (filters->>'published_to' is null or k.published_on <= (filters->>'published_to')::date)
), evidence as (
    select c.source_url, o.observation_id id,o.evidence_kind kind,o.locator,o.verbatim body
    from corpus c join reelbrain_research.reel_observations o using(source_url)
    union all select c.source_url,'caption','caption','creator-caption',c.caption from corpus c
    union all select c.source_url,'speech','speech','hosted-asr',c.transcript->>'text' from corpus c
    union all select c.source_url,'speech:'||s.i,'third_party_speech_segment',concat('hosted-asr:',s.part->>'start','–',s.part->>'end','s'),s.part->>'text'
    from corpus c cross join lateral jsonb_array_elements(case when jsonb_typeof(c.transcript->'segments')='array' then c.transcript->'segments' else '[]'::jsonb end) with ordinality s(part,i)
    union all select c.source_url,'research','external_topic_research','saved external research',nullif(c.research::text,'{}') from corpus c
    union all select c.source_url,'resource:'||md5(r.canonical_resource_url||r.observation_id),'resource:'||coalesce(r.verification_level,'unverified'),
      coalesce(o.locator,'resource'),concat_ws(' ',r.resource_name,r.canonical_resource_url,r.claimed_purpose)
    from corpus c join reelbrain_research.reel_resources r using(source_url)
    left join reelbrain_research.reel_observations o on o.source_url=r.source_url and o.observation_id=r.observation_id
), scored as (
    select e.*, (select count(*) from unnest(words[1:24]) w where w<>'' and strpos(lower(e.body),w)>0) score,
       bool_or(filters->>'tool' is null or strpos(lower(e.body),lower(filters->>'tool'))>0) over(partition by source_url) tool_ok
    from evidence e where length(trim(body))>0 and body not in ('[]','null')
), dedup as (
    select distinct on(source_url,kind,md5(body)) * from scored
    where tool_ok and (selected is not null or score>0)
    order by source_url,kind,md5(body),score desc,id
), ranked as (
    select *,row_number() over(partition by source_url order by score desc,case when kind='caption' then 0 when kind like 'resource:%' then 1 else 2 end,id) rn from dedup
), cards as (
    select c.source_url,max(r.score) best,jsonb_build_object('source',c.source_url,'creator',c.creator,'published',c.published,'saved',c.saved,'status',c.status,
      'evidence',jsonb_agg(jsonb_build_object('id',r.id,'kind',r.kind,'locator',r.locator,'text',left(r.body,1800)) order by r.rn)) card
    from corpus c join ranked r using(source_url) where r.rn<=8 group by c.source_url,c.creator,c.published,c.saved,c.status
)
select card,count(*) over() from cards order by best desc,source_url
limit least(greatest(page_limit,1),20) offset greatest(page_offset,0)
$$;
revoke all on function reelbrain_studio.hosted_search(text[],jsonb,text[],integer,integer) from public,anon,authenticated;
grant execute on function reelbrain_studio.hosted_search(text[],jsonb,text[],integer,integer) to reelbrain_studio_app;
