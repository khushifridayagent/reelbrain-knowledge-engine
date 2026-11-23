-- Applied only to NEW isolated Supabase project xlkdzrhzizuftbnitodr.
-- A README read is proof of published claims, NOT proof of operational capability.
CREATE TABLE IF NOT EXISTS reelbrain_research.repository_verifications (
 archive_sha text NOT NULL,catalog_number integer NOT NULL,repo text NOT NULL,
 github_repository_id text,checked_at timestamptz NOT NULL DEFAULT now(),
 readme_url text NOT NULL,readme_blob_sha text NOT NULL,
 readme_claims text NOT NULL,
 verification_level text NOT NULL CHECK(verification_level IN ('github_exists','readme_checked')),
 execution_status text NOT NULL DEFAULT 'not_tested' CHECK(execution_status IN ('not_tested','sandbox_tested')),
 PRIMARY KEY(archive_sha,catalog_number,readme_blob_sha),
 FOREIGN KEY(archive_sha,catalog_number) REFERENCES reelbrain_research.catalog(archive_sha,catalog_number)
);
CREATE INDEX IF NOT EXISTS research_verification_repo_idx ON reelbrain_research.repository_verifications(repo,checked_at DESC);
ALTER TABLE reelbrain_research.repository_verifications ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON reelbrain_research.repository_verifications FROM PUBLIC,anon,authenticated;
