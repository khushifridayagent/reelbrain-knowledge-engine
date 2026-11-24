-- Ensure every Reel caption, distinct external-topic research, and optional
-- third-party speech transcript is retrievable *before* original media access.
-- Distinguish direct visual evidence, public metadata, independent research and
-- hosted ASR: a URL-first provider transcript is NOT a frame verification.
-- Search remains in the isolated private schema; no unauthenticated grants.
CREATE OR REPLACE FUNCTION reelbrain_research.search_reels(
    query_text text, max_results integer DEFAULT 15
)
RETURNS TABLE(
  repo text, repo_url text, what_it_does text,
  core_features text, practical_use_cases text,
  verification_level text, source_locator text, search_rank real
)
LANGUAGE sql STABLE SET search_path TO ''
AS $search$
WITH q AS (
  SELECT websearch_to_tsquery('simple'::regconfig,
          left(coalesce(query_text,''),180)) AS query
  WHERE length(trim(coalesce(query_text,''))) >= 2
),
items AS (
  -- Real OCR/ASR derived resource observations.
  SELECT r.resource_name AS repo, r.canonical_resource_url AS repo_url,
         r.claimed_purpose AS what_it_does,
         'Source-observed resource; independent features not verified'::text AS core_features,
         'See source Reel and evidence before using'::text AS practical_use_cases,
         r.verification_level AS verification_level,
         r.source_url||' @ '||o.locator AS source_locator,
         to_tsvector('simple'::regconfig,
             coalesce(r.resource_name,'')||' '||
             coalesce(r.claimed_purpose,'')||' '||
             coalesce(r.canonical_resource_url,'')) AS doc
  FROM reelbrain_research.reel_resources r
  JOIN reelbrain_research.reel_observations o
    ON o.source_url=r.source_url AND o.observation_id=r.observation_id

  UNION ALL

  -- A public creator caption is searchable, never audio/video proof.
  SELECT coalesce(nullif(k.creator_handle,''),'Instagram Reel')::text,
         k.source_url,
         left(coalesce(k.caption,''),4000),
         'Creator-caption claims only; original media not independently verified'::text,
         'Review original source and independent evidence'::text,
         'public_instagram_metadata'::text,
         k.source_url||' @ creator-caption',
         to_tsvector('simple'::regconfig, coalesce(k.creator_handle,'')||' '||coalesce(k.caption,''))
  FROM public.reelbrain_reel_knowledge k
  WHERE length(trim(coalesce(k.caption,''))) > 0

  UNION ALL

  -- Independent repository/doc facts belong to a separate provenance tier.
  SELECT coalesce(nullif(k.creator_handle,''),'Independent Reel research')::text,
         k.source_url,
         left(coalesce(k.external_topic_research::text,''),4000),
         'Independent external-topic research, not claims proven inside Reel'::text,
         'Verify the referenced documentation before relying on it'::text,
         'external_topic_research'::text,
         k.source_url||' @ external-topic-research',
         to_tsvector('simple'::regconfig, coalesce(k.external_topic_research::text,''))
  FROM public.reelbrain_reel_knowledge k
  WHERE k.external_topic_research IS NOT NULL
    AND k.external_topic_research <> '{}'::jsonb

  UNION ALL

  -- Optional URL-first provider transcript; NOT first-party audio observation.
  SELECT coalesce(nullif(k.creator_handle,''),'Instagram Reel')::text,
         k.source_url,
         left(coalesce(k.verified_reel_content->'provider_audio_transcript'->>'text',''),4000),
         'Third-party ASR from a public Reel URL; NOT independently verified media'::text,
         'Timestamp claims are provider supplied, where available'::text,
         'third_party_url_speech_transcript'::text,
         k.source_url||' @ hosted-asr:transcript',
         to_tsvector('simple'::regconfig,
             coalesce(k.verified_reel_content->'provider_audio_transcript'->>'text',''))
  FROM public.reelbrain_reel_knowledge k
  WHERE length(trim(coalesce(
      k.verified_reel_content->'provider_audio_transcript'->>'text',''))) > 0
)
SELECT i.repo,i.repo_url,i.what_it_does,i.core_features,
       i.practical_use_cases,i.verification_level,i.source_locator,
       ts_rank_cd(i.doc,q.query)::real AS search_rank
FROM items i CROSS JOIN q
WHERE i.doc @@ q.query
ORDER BY search_rank DESC, i.repo_url, i.verification_level
LIMIT least(greatest(coalesce(max_results,15),1),50);
$search$;
