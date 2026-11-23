-- Applied ONLY to isolated Reelbrain Knowledge project xlkdzrhzizuftbnitodr.
-- Every accepted sender MESSAGE gets a receipt, even if it cannot be parsed into a Reel URL.
-- Reel jobs are deduplicated by canonical URL; receipts are deduplicated by (sender, message id).
-- No private DM text is persisted in these tables; Meta message ID is retained for reconciliation.
CREATE TABLE IF NOT EXISTS public.reelbrain_dm_receipts (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  sender_igsid text NOT NULL REFERENCES public.reelbrain_sender_candidates(sender_id),
  message_id text NOT NULL CHECK (length(message_id) BETWEEN 1 AND 256),
  message_digest text NOT NULL CHECK (length(message_digest)=64),
  status text NOT NULL CHECK (status IN ('queued','needs_review','no_reel_link')),
  attachment_types jsonb NOT NULL DEFAULT '[]'::jsonb,
  first_received_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(sender_igsid,message_id)
);
CREATE TABLE IF NOT EXISTS public.reelbrain_dm_receipt_links (
  receipt_id bigint NOT NULL REFERENCES public.reelbrain_dm_receipts(id) ON DELETE CASCADE,
  source_url text NOT NULL REFERENCES public.reelbrain_dm_jobs(source_url),
  PRIMARY KEY(receipt_id,source_url)
);
CREATE INDEX IF NOT EXISTS reelbrain_dm_receipts_attention_idx ON public.reelbrain_dm_receipts(status,first_received_at)
 WHERE status='needs_review';
CREATE INDEX IF NOT EXISTS reelbrain_dm_receipts_sender_idx ON public.reelbrain_dm_receipts(sender_igsid,first_received_at DESC);
ALTER TABLE public.reelbrain_dm_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reelbrain_dm_receipt_links ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reelbrain_dm_receipts, public.reelbrain_dm_receipt_links FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.reelbrain_dm_receipts_id_seq FROM PUBLIC, anon, authenticated;
GRANT SELECT,INSERT,UPDATE ON public.reelbrain_dm_receipts TO service_role;
GRANT SELECT,INSERT ON public.reelbrain_dm_receipt_links TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.reelbrain_dm_receipts_id_seq TO service_role;

CREATE OR REPLACE FUNCTION public.reelbrain_accept_dm_batch(_events jsonb)
RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=''
AS $$
DECLARE
  ev jsonb;
  raw_url jsonb;
  sender_id text;
  mid text;
  source text;
  receipt bigint;
  total_received integer:=0;
  new_received integer:=0;
  linked integer:=0;
  needs_review integer:=0;
  approved_sender boolean;
  msg_status text;
  accepted_urls jsonb;
  types jsonb;
BEGIN
  IF jsonb_typeof(_events) <> 'array' OR jsonb_array_length(_events)>100 THEN
    RAISE EXCEPTION 'invalid event batch';
  END IF;
  FOR ev IN SELECT value FROM pg_catalog.jsonb_array_elements(_events)
  LOOP
    sender_id := ev->>'sid'; mid:=ev->>'mid'; msg_status:=ev->>'status';
    accepted_urls:=ev->'urls'; types:=COALESCE(ev->'attachment_types','[]'::jsonb);
    IF sender_id IS NULL OR mid IS NULL OR length(mid) NOT BETWEEN 1 AND 256
       OR msg_status IS NULL OR msg_status NOT IN ('queued','needs_review','no_reel_link')
       OR jsonb_typeof(accepted_urls) <> 'array' OR jsonb_array_length(accepted_urls)>12
       OR jsonb_typeof(types) <> 'array' OR jsonb_array_length(types)>20 THEN
      RAISE EXCEPTION 'invalid event format';
    END IF;
    SELECT c.approved INTO approved_sender FROM public.reelbrain_sender_candidates c WHERE c.sender_id=(ev->>'sid');
    IF approved_sender IS DISTINCT FROM true THEN
      RAISE EXCEPTION 'unknown/unapproved sender';
    END IF;
    IF (jsonb_array_length(accepted_urls)>0 AND msg_status<>'queued') OR
       (jsonb_array_length(accepted_urls)=0 AND msg_status='queued') THEN
      RAISE EXCEPTION 'message URL/status mismatch';
    END IF;
    total_received:=total_received+1;
    receipt:=NULL;
    INSERT INTO public.reelbrain_dm_receipts(sender_igsid,message_id,message_digest,status,attachment_types)
    VALUES(sender_id,mid,pg_catalog.encode(extensions.digest(mid,'sha256'),'hex'),msg_status,types)
    ON CONFLICT (sender_igsid,message_id) DO NOTHING RETURNING id INTO receipt;
    IF receipt IS NOT NULL THEN
      new_received:=new_received+1;
      IF msg_status='needs_review' THEN needs_review:=needs_review+1; END IF;
    ELSE
      SELECT id INTO receipt FROM public.reelbrain_dm_receipts WHERE sender_igsid=sender_id AND message_id=mid;
      IF msg_status='queued' THEN
        UPDATE public.reelbrain_dm_receipts SET status='queued' WHERE id=receipt AND status<>'queued';
      END IF;
    END IF;
    FOR raw_url IN SELECT value FROM pg_catalog.jsonb_array_elements(accepted_urls)
    LOOP
      IF jsonb_typeof(raw_url)<>'string' THEN RAISE EXCEPTION 'URL must be string'; END IF;
      source:=raw_url #>> '{}';
      IF source !~ '^https://www\.instagram\.com/(reel|p|tv)/[A-Za-z0-9_-]{4,160}/$' THEN
        RAISE EXCEPTION 'noncanonical Instagram URL';
      END IF;
      INSERT INTO public.reelbrain_dm_jobs(source_url,inbound_event_id,sender_digest)
      VALUES(source,pg_catalog.encode(extensions.digest(mid,'sha256'),'hex'),pg_catalog.encode(extensions.digest(sender_id,'sha256'),'hex'))
      ON CONFLICT (source_url) DO NOTHING;
      INSERT INTO public.reelbrain_dm_receipt_links(receipt_id,source_url)
      VALUES(receipt,source) ON CONFLICT DO NOTHING;
      linked:=linked+1;
    END LOOP;
  END LOOP;
  RETURN pg_catalog.jsonb_build_object('received_messages',total_received,'new_receipts',new_received,
      'reel_links_seen',linked,'new_unresolved_receipts',needs_review);
END;
$$;
REVOKE ALL ON FUNCTION public.reelbrain_accept_dm_batch(jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.reelbrain_accept_dm_batch(jsonb) TO service_role;