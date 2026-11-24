-- A received Reel is always queued; provider free credits are the execution
-- throttle. 60/day was a *user example* not a source-throughput limit.
-- TranscriptFetch is preflighted with free GET /api/v2/me and the paid API
-- itself refuses overage (402), so usage is audited instead of hard-capped.
-- Existing user-approved ScrapeCreators mode RETAINS its bounded daily cap.
ALTER TABLE reelbrain_research.hosted_transcript_daily_budget
 DROP CONSTRAINT IF EXISTS hosted_transcript_daily_budget_reserved_calls_check;
ALTER TABLE reelbrain_research.hosted_transcript_daily_budget
 ADD CONSTRAINT hosted_transcript_daily_budget_reserved_calls_check
 CHECK (reserved_calls >= 0);
REVOKE ALL ON reelbrain_research.hosted_transcript_daily_budget FROM PUBLIC,anon,authenticated;
