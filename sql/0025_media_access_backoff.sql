-- Already applied to the isolated Supabase project xlkdzrhzizuftbnitodr.
-- Public network rate limiting should not irreversibly exhaust all media jobs.
ALTER TABLE public.reelbrain_dm_jobs
  ADD COLUMN IF NOT EXISTS access_deferred_count integer NOT NULL DEFAULT 0;

CREATE OR REPLACE FUNCTION public.reelbrain_defer_dm_job(
  job_id bigint, token uuid, reason text, seconds_to_wait integer DEFAULT 14400
)
RETURNS boolean
LANGUAGE sql
SET search_path=''
AS $$
WITH changed AS (
  UPDATE public.reelbrain_dm_jobs
  SET status='queued',
      attempts=GREATEST(0,attempts-1),
      access_deferred_count=LEAST(2147483646,access_deferred_count+1),
      available_at=now()+make_interval(
        secs=>LEAST(86400,GREATEST(900,COALESCE(seconds_to_wait,14400)))),
      lease_token=NULL, lease_until=NULL, updated_at=now(),
      last_error=LEFT(COALESCE(reason,'Media access temporarily unavailable'),400)
  WHERE id=job_id AND status='leased' AND lease_token=token
  RETURNING id
)
SELECT EXISTS(SELECT 1 FROM changed);
$$;

REVOKE ALL ON FUNCTION public.reelbrain_defer_dm_job(bigint,uuid,text,integer)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.reelbrain_defer_dm_job(bigint,uuid,text,integer)
  TO service_role, postgres;
