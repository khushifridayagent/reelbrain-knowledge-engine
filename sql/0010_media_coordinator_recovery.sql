-- Deploy ONLY on isolated Supabase project xlkdzrhzizuftbnitodr.
-- Does not acquire video/audio, call paid provider, or consume any media queue attempt.
-- Migrations 0005, 0007, 0009 and approved sender receipts must already be present.
CREATE TABLE IF NOT EXISTS public.reelbrain_worker_state (
 worker_name text PRIMARY KEY CHECK(worker_name='coordinator'),
 last_tick timestamptz NOT NULL DEFAULT now(),
 last_result jsonb NOT NULL DEFAULT '{}'::jsonb,
 last_error text,
 full_media_host_connected boolean NOT NULL DEFAULT false,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.reelbrain_media_tick_tokens (
 token_hash text PRIMARY KEY CHECK(token_hash ~ '^[0-9a-f]{64}$'),
 expires_at timestamptz NOT NULL,
 used_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS reelbrain_media_tick_token_cleanup ON public.reelbrain_media_tick_tokens(expires_at);
ALTER TABLE public.reelbrain_worker_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reelbrain_media_tick_tokens ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reelbrain_worker_state, public.reelbrain_media_tick_tokens FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.reelbrain_worker_state,public.reelbrain_media_tick_tokens TO service_role;

CREATE OR REPLACE FUNCTION public.reelbrain_claim_media_tick(hash_arg text)
RETURNS boolean LANGUAGE sql VOLATILE SECURITY INVOKER SET search_path=''
AS $$
 WITH claimed AS (
   UPDATE public.reelbrain_media_tick_tokens SET used_at=now()
     WHERE token_hash=hash_arg AND used_at IS NULL AND expires_at>now()
     RETURNING token_hash
 ) SELECT EXISTS(SELECT 1 FROM claimed);
$$;
REVOKE ALL ON FUNCTION public.reelbrain_claim_media_tick(text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.reelbrain_claim_media_tick(text) TO service_role;

-- Atomic per-tick creation of evidence-accurate placeholders. Never mark done.
CREATE OR REPLACE FUNCTION public.reelbrain_prepare_media_batch(batch_size integer DEFAULT 30)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=''
AS $$
DECLARE
 inserted_count integer:=0;
 transitioned_count integer:=0;
 queued_count integer:=0;
 dead_count integer:=0;
 unresolved_count integer:=0;
 limit_count integer:=least(greatest(coalesce(batch_size,30),1),50);
BEGIN
 WITH pending AS (
   SELECT source_url FROM public.reelbrain_dm_jobs
    WHERE status IN ('queued','leased')
    ORDER BY created_at,id LIMIT limit_count
 ), inserted AS (
   INSERT INTO public.reelbrain_reel_knowledge
    (source_url,source_provider,processing_stage,verified_reel_content,content_evidence)
   SELECT source_url,'meta_instagram_dm_webhook','media_pending',
     '{"note":"Verified Reel URL only. Original video and audio have NOT yet been retrieved or analyzed."}'::jsonb,
     '[{"kind":"signed_instagram_dm","evidence_level":"reel_url_only","visual_analysis":false}]'::jsonb
    FROM pending ON CONFLICT(source_url) DO NOTHING RETURNING source_url
 ) SELECT count(*) INTO inserted_count FROM inserted;
 WITH changed AS (
   UPDATE public.reelbrain_reel_knowledge k
    SET processing_stage='media_pending',updated_at=now()
    WHERE k.processing_stage='metadata_only'
      AND k.source_url IN (
        SELECT j.source_url FROM public.reelbrain_dm_jobs j
        WHERE j.status IN ('queued','leased') ORDER BY j.created_at LIMIT limit_count)
    RETURNING source_url
 ) SELECT count(*) INTO transitioned_count FROM changed;
 SELECT count(*) INTO queued_count FROM public.reelbrain_dm_jobs WHERE status IN ('queued','leased');
 SELECT count(*) INTO dead_count FROM public.reelbrain_dm_jobs WHERE status='dead_letter';
 SELECT count(*) INTO unresolved_count FROM public.reelbrain_dm_receipts WHERE status='needs_review';
 RETURN jsonb_build_object('created_media_pending',inserted_count,'metadata_updated_to_pending',transitioned_count,
        'queued_or_leased',queued_count,'dead_letter',dead_count,'unresolved_receipts',unresolved_count,
        'media_worker_deployed',false);
END;
$$;
REVOKE ALL ON FUNCTION public.reelbrain_prepare_media_batch(integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.reelbrain_prepare_media_batch(integer) TO service_role;

-- Called by pg_cron only (postgres role); the secret is ONE-USE, 8-minute expiry,
-- hashed at rest and never committed to source or saved in logs.
CREATE OR REPLACE FUNCTION public.reelbrain_dispatch_media_tick()
RETURNS bigint LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=''
AS $$
DECLARE
 nonce text:=encode(extensions.gen_random_bytes(32),'hex');
 req_id bigint;
BEGIN
 INSERT INTO public.reelbrain_media_tick_tokens(token_hash,expires_at)
 VALUES (encode(extensions.digest(nonce,'sha256'),'hex'),now()+interval '8 minutes');
 SELECT net.http_post(
  url:='https://xlkdzrhzizuftbnitodr.supabase.co/functions/v1/reelbrain-knowledge-coordinator',
  body:=jsonb_build_object('nonce',nonce),
  headers:='{"Content-Type":"application/json"}'::jsonb,
  timeout_milliseconds:=25000
 ) INTO req_id;
 RETURN req_id;
END;
$$;
REVOKE ALL ON FUNCTION public.reelbrain_dispatch_media_tick() FROM PUBLIC,anon,authenticated,service_role;

-- Keep token table bounded; called by the same cron scheduled job.
CREATE OR REPLACE FUNCTION public.reelbrain_cleanup_media_ticks()
RETURNS integer LANGUAGE sql VOLATILE SECURITY INVOKER SET search_path=''
AS $$
 WITH gone AS (DELETE FROM public.reelbrain_media_tick_tokens
  WHERE expires_at<now()-interval '1 day' RETURNING token_hash)
 SELECT count(*)::integer FROM gone;
$$;
REVOKE ALL ON FUNCTION public.reelbrain_cleanup_media_ticks() FROM PUBLIC,anon,authenticated,service_role;