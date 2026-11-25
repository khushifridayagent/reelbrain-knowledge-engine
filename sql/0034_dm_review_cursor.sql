-- Additive, scoped recovery progress only; no receipt or job state changes.
ALTER TABLE public.reelbrain_dm_reconciliation_state ADD COLUMN IF NOT EXISTS review_cursor bigint NOT NULL DEFAULT 0;
