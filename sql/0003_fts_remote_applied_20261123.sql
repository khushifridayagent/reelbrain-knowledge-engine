-- VERIFIED APPLIED on NEW project Reelbrain Knowledge (xlkdzrhzizuftbnitodr) ONLY.
-- DO NOT run against GTA VI or any existing unrelated project.
CREATE INDEX IF NOT EXISTS reelbrain_catalog_fts_simple_gin
ON reelbrain_research.catalog
USING GIN (to_tsvector('simple'::regconfig,
 coalesce(repo,'') || ' ' || coalesce(repo_url,'') || ' ' ||
 coalesce(what_it_does,'') || ' ' || coalesce(core_features,'') || ' ' ||
 coalesce(practical_use_cases,'')));

CREATE OR REPLACE FUNCTION reelbrain_research.search_catalog_indexed(
 query_text text, max_results integer DEFAULT 20
) RETURNS TABLE (
 repo text, repo_url text, what_it_does text, core_features text,
 practical_use_cases text, verification_level text,
 source_locator text, archive_sha text, search_rank real
)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = '' AS $$
 SELECT c.repo,c.repo_url,c.what_it_does,c.core_features,
        c.practical_use_cases,c.verification_level,c.source_locator,c.archive_sha,
        ts_rank_cd(to_tsvector('simple'::regconfig,
          coalesce(c.repo,'') || ' ' || coalesce(c.repo_url,'') || ' ' ||
          coalesce(c.what_it_does,'') || ' ' || coalesce(c.core_features,'') || ' ' ||
          coalesce(c.practical_use_cases,'')),
          websearch_to_tsquery('simple'::regconfig,LEFT(query_text,180)))::real AS search_rank
 FROM reelbrain_research.catalog AS c
 WHERE length(trim(coalesce(query_text,'')))>0
   AND to_tsvector('simple'::regconfig,
          coalesce(c.repo,'') || ' ' || coalesce(c.repo_url,'') || ' ' ||
          coalesce(c.what_it_does,'') || ' ' || coalesce(c.core_features,'') || ' ' ||
          coalesce(c.practical_use_cases,''))
       @@ websearch_to_tsquery('simple'::regconfig,LEFT(query_text,180))
 ORDER BY CASE WHEN lower(c.repo)=lower(query_text) THEN 0 ELSE 1 END,
          search_rank DESC,c.repo
 LIMIT LEAST(GREATEST(coalesce(max_results,20),1),50);
$$;
REVOKE ALL ON FUNCTION reelbrain_research.search_catalog_indexed(text,integer)
 FROM PUBLIC, anon, authenticated;
