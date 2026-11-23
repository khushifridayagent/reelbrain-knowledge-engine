-- THIS SQL WAS APPLIED ONLY TO THE BRAND-NEW SUPABASE PROJECT:
--   Reelbrain Knowledge / ap-south-1 / xlkdzrhzizuftbnitodr
-- NEVER RUN AGAINST GTA VI OR OTHER EXISTING PROJECT DATABASES.
-- No destructive SQL; no new public Data API surface.
CREATE SCHEMA IF NOT EXISTS reelbrain_research;
REVOKE ALL ON SCHEMA reelbrain_research FROM PUBLIC, anon, authenticated;
CREATE TABLE IF NOT EXISTS reelbrain_research.archives (
 archive_sha text PRIMARY KEY CHECK (length(archive_sha)=64),
 archive_name text NOT NULL, source_id text NOT NULL,
 coverage_json jsonb NOT NULL DEFAULT '{}'::jsonb,
 verified_manifest_count integer NOT NULL CHECK (verified_manifest_count>=0),
 imported_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS reelbrain_research.catalog (
 archive_sha text NOT NULL REFERENCES reelbrain_research.archives(archive_sha),
 repo text NOT NULL, catalog_number integer NOT NULL CHECK (catalog_number>=1),
 repo_url text NOT NULL CHECK (repo_url LIKE 'https://github.com/%'),
 what_it_does text NOT NULL, core_features text NOT NULL, practical_use_cases text NOT NULL,
 evidence text NOT NULL, source_verification text NOT NULL,
 verification_level text NOT NULL DEFAULT 'supplied_unverified'
 CHECK(verification_level IN ('supplied_unverified','github_exists','readme_checked','sandbox_run','user_confirmed')),
 source_locator text NOT NULL, PRIMARY KEY(archive_sha,catalog_number)
);
CREATE TABLE IF NOT EXISTS reelbrain_research.daily_leaders (
 archive_sha text NOT NULL REFERENCES reelbrain_research.archives(archive_sha),
 day date NOT NULL,row_json jsonb NOT NULL,PRIMARY KEY(archive_sha,day)
);
CREATE TABLE IF NOT EXISTS reelbrain_research.ranked_entries (
 archive_sha text NOT NULL REFERENCES reelbrain_research.archives(archive_sha),
 day date NOT NULL,source text NOT NULL,rank integer NOT NULL CHECK(rank>=0),
 repo text NOT NULL,row_json jsonb NOT NULL,PRIMARY KEY(archive_sha,day,source,rank,repo)
);
CREATE TABLE IF NOT EXISTS reelbrain_research.capture_provenance (
 archive_sha text NOT NULL REFERENCES reelbrain_research.archives(archive_sha),
 day date NOT NULL,source text NOT NULL,row_json jsonb NOT NULL,
 PRIMARY KEY(archive_sha,day,source)
);
CREATE INDEX IF NOT EXISTS research_catalog_name_idx ON reelbrain_research.catalog(lower(repo));
CREATE INDEX IF NOT EXISTS research_ranked_repo_idx ON reelbrain_research.ranked_entries(repo,day);
CREATE INDEX IF NOT EXISTS research_daily_day_idx ON reelbrain_research.daily_leaders(day);
ALTER TABLE reelbrain_research.archives ENABLE ROW LEVEL SECURITY;
ALTER TABLE reelbrain_research.catalog ENABLE ROW LEVEL SECURITY;
ALTER TABLE reelbrain_research.daily_leaders ENABLE ROW LEVEL SECURITY;
ALTER TABLE reelbrain_research.ranked_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE reelbrain_research.capture_provenance ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA reelbrain_research FROM PUBLIC,anon,authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA reelbrain_research FROM PUBLIC,anon,authenticated;
