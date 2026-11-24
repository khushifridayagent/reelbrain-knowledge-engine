-- Isolated URL-first hosted speech stage.
-- No public/anon/authenticated access. No raw media or provider keys stored.
CREATE TABLE IF NOT EXISTS reelbrain_research.hosted_transcript_attempts (
    source_url text PRIMARY KEY REFERENCES public.reelbrain_reel_knowledge(source_url)
        ON DELETE CASCADE,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 3),
    state text NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending','claimed','retry','no_speech','completed')),
    provider text NOT NULL DEFAULT 'scrapecreators',
    last_attempt_at timestamptz,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    last_category text,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS reelbrain_research.hosted_transcript_daily_budget (
    usage_day date PRIMARY KEY,
    reserved_calls integer NOT NULL DEFAULT 0 CHECK (reserved_calls BETWEEN 0 AND 2),
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE reelbrain_research.hosted_transcript_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE reelbrain_research.hosted_transcript_daily_budget ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON reelbrain_research.hosted_transcript_attempts FROM PUBLIC, anon, authenticated;
REVOKE ALL ON reelbrain_research.hosted_transcript_daily_budget FROM PUBLIC, anon, authenticated;
