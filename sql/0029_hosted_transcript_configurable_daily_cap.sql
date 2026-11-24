-- Allow planned bursts while keeping default 2 requests/day.
-- A GitHub variable can raise this ONLY with explicit budget approval;
-- SQL still refuses more than 120 provider starts per UTC day.
ALTER TABLE reelbrain_research.hosted_transcript_daily_budget
  DROP CONSTRAINT IF EXISTS hosted_transcript_daily_budget_reserved_calls_check;
ALTER TABLE reelbrain_research.hosted_transcript_daily_budget
  ADD CONSTRAINT hosted_transcript_daily_budget_reserved_calls_check
  CHECK (reserved_calls BETWEEN 0 AND 120);
REVOKE ALL ON reelbrain_research.hosted_transcript_daily_budget
  FROM PUBLIC,anon,authenticated;
