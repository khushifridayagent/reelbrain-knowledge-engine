-- Private, evidence-first per-timestamp retrieval of real provider speech.
-- Retains provider attribution. A creator caption / independent research is
-- NEVER substituted for an actual spoken segment, and an ASR result cannot
-- prove visual frames/URLs.
CREATE OR REPLACE FUNCTION reelbrain_research.search_reel_speech_segments(
  query_text text, max_results integer DEFAULT 20
)
RETURNS TABLE(
  source_url text,
  provider text,
  start_seconds double precision,
  end_seconds double precision,
  spoken_text text,
  evidence_kind text,
  search_rank real
)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = ''
AS $fn$
  WITH q AS (
    SELECT websearch_to_tsquery('simple'::regconfig,
           left(trim(coalesce(query_text,'')),180)) AS words
    WHERE length(trim(coalesce(query_text,'')))>=2
  ),
  segments AS (
    SELECT k.source_url,
           coalesce(k.verified_reel_content->'provider_audio_transcript'->>'provider','unknown') AS provider,
           NULLIF(s.part->>'start','')::double precision AS start_seconds,
           NULLIF(s.part->>'end','')::double precision AS end_seconds,
           left(s.part->>'text',5000)::text AS spoken_text,
           to_tsvector('simple'::regconfig,coalesce(s.part->>'text','')) AS doc
      FROM public.reelbrain_reel_knowledge k
      CROSS JOIN LATERAL jsonb_array_elements(
           CASE WHEN jsonb_typeof(k.verified_reel_content->'provider_audio_transcript'->'segments')='array'
                THEN k.verified_reel_content->'provider_audio_transcript'->'segments'
                ELSE '[]'::jsonb END) s(part)
      WHERE jsonb_typeof(s.part)='object'
        AND jsonb_typeof(s.part->'text')='string'
        AND length(trim(coalesce(s.part->>'text','')))>0
  )
  SELECT t.source_url,t.provider,t.start_seconds,t.end_seconds,
         t.spoken_text,
         'third_party_url_speech_segment'::text AS evidence_kind,
         ts_rank_cd(t.doc,q.words)::real AS search_rank
  FROM segments t CROSS JOIN q
  WHERE t.doc @@ q.words
  ORDER BY search_rank DESC, t.source_url,t.start_seconds
  LIMIT least(greatest(coalesce(max_results,20),1),50);
$fn$;
REVOKE ALL ON FUNCTION reelbrain_research.search_reel_speech_segments(text,integer)
FROM PUBLIC,anon,authenticated;
