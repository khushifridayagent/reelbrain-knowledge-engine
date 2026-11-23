-- Reproducible schedules for ONLY isolated Supabase project xlkdzrhzizuftbnitodr.
-- Requires 0010, 0011, Supabase pg_net extension and both deployed Edge Functions.
-- Reconciliation and coordinator are *lightweight*: full video/media worker needs a host.
CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;
SELECT cron.schedule(
  'reelbrain-metadata-coordinator','*/5 * * * *',
  'SELECT public.reelbrain_dispatch_media_tick();'
);
SELECT cron.schedule(
  'reelbrain-tick-token-cleanup','0 * * * *',
  'SELECT public.reelbrain_cleanup_media_ticks();'
);
-- Exactly one of the 3 approved personal senders per 5-minute run;
-- each account is checked about once every 15 minutes.
SELECT cron.schedule('reelbrain-three-approved-sender-reconcile','*/5 * * * *',
  $$SELECT public.reelbrain_dispatch_dm_reconcile(
     CASE ((extract(minute FROM now())::integer / 5) % 3)
       WHEN 0 THEN 'rudrzy'
       WHEN 1 THEN 'rudra_625003'
       ELSE 'hritiksingh_8'
     END
   );$$
);