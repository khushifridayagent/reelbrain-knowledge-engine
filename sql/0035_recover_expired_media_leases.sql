-- Isolated ReelBrain only. Match the worker's crash-recovery semantics.
-- An expired runner lease is not evidence of a failed source. Preserve the
-- original retry budget and all persisted evidence; never touch active leases.
create or replace function public.reelbrain_reap_expired_dm_jobs(batch_size integer default 100)
returns integer language sql volatile security invoker set search_path = ''
as $$
  with selected as (
    select id from public.reelbrain_dm_jobs
    where status='leased' and lease_until<now()
    order by lease_until,id for update skip locked
    limit least(greatest(coalesce(batch_size,100),1),500)
  ), changed as (
    update public.reelbrain_dm_jobs j
    set status='queued', attempts=greatest(0,attempts-1),
        lease_token=null,lease_until=null,available_at=now(),updated_at=now(),
        last_error='Previous runner lease expired; resume pending stages'
    from selected where j.id=selected.id
      and j.status='leased' and j.lease_until<now()
    returning j.id
  ) select count(*)::integer from changed;
$$;
revoke all on function public.reelbrain_reap_expired_dm_jobs(integer) from public,anon,authenticated;
grant execute on function public.reelbrain_reap_expired_dm_jobs(integer) to service_role;
