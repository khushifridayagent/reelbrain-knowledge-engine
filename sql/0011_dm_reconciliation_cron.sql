-- Only isolated Reelbrain Knowledge project xlkdzrhzizuftbnitodr.
-- Official Meta Graph reconciliation for three approved 1:1 senders. No group reads.
CREATE TABLE IF NOT EXISTS public.reelbrain_dm_reconciliation_state (
 sender_igsid text PRIMARY KEY REFERENCES public.reelbrain_sender_candidates(sender_id),
 last_checked_at timestamptz NOT NULL DEFAULT now(),
 last_new_receipts integer NOT NULL DEFAULT 0,
 last_error text
);
ALTER TABLE public.reelbrain_dm_reconciliation_state ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reelbrain_dm_reconciliation_state FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.reelbrain_dm_reconciliation_state TO service_role;

CREATE OR REPLACE FUNCTION public.reelbrain_dispatch_dm_reconcile(sender_name text)
RETURNS bigint LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=''
AS $$
DECLARE nonce text:=encode(extensions.gen_random_bytes(32),'hex');request_id bigint;
BEGIN
 IF sender_name NOT IN ('rudrzy','rudra_625003','hritiksingh_8') THEN RAISE EXCEPTION 'unapproved reconciliation target'; END IF;
 INSERT INTO public.reelbrain_media_tick_tokens(token_hash,expires_at)
 VALUES (encode(extensions.digest(nonce,'sha256'),'hex'),now()+interval '8 minutes');
 SELECT net.http_post(
   url:='https://xlkdzrhzizuftbnitodr.supabase.co/functions/v1/reelbrain-dm-reconciler',
   body:=jsonb_build_object('nonce',nonce,'sender_username',sender_name),headers:='{"Content-Type":"application/json"}'::jsonb,
   timeout_milliseconds:=70000
 ) INTO request_id;
 RETURN request_id;
END;
$$;
REVOKE ALL ON FUNCTION public.reelbrain_dispatch_dm_reconcile(text) FROM PUBLIC,anon,authenticated,service_role;