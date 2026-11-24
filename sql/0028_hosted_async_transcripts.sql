-- Hosted transcript API v2 returns 202 with a durable job_id. Poll without
-- burning a new reservation or making duplicate billable start requests.
-- Scope is the isolated Reelbrain research schema, never the public Data API.
ALTER TABLE reelbrain_research.hosted_transcript_attempts
  ADD COLUMN IF NOT EXISTS provider_job_id text,
  ADD COLUMN IF NOT EXISTS last_poll_at timestamptz;
ALTER TABLE reelbrain_research.hosted_transcript_attempts
  DROP CONSTRAINT IF EXISTS hosted_transcript_attempts_state_check;
ALTER TABLE reelbrain_research.hosted_transcript_attempts
  ADD CONSTRAINT hosted_transcript_attempts_state_check
  CHECK (state IN ('pending','claimed','retry','no_speech','completed','processing'));
ALTER TABLE reelbrain_research.hosted_transcript_attempts
  ADD CONSTRAINT hosted_transcript_attempts_provider_job_id_check
  CHECK (provider_job_id IS NULL OR provider_job_id ~ '^asr_[A-Za-z0-9_-]{3,80}$');
CREATE INDEX IF NOT EXISTS ix_reelbrain_transcript_poll
  ON reelbrain_research.hosted_transcript_attempts (next_attempt_at)
  WHERE state='processing';
REVOKE ALL ON reelbrain_research.hosted_transcript_attempts FROM PUBLIC, anon, authenticated;
