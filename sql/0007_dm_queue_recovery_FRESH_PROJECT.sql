-- Isolated new Reelbrain project only. Expired final-attempt leases must not remain stuck forever.
create or replace function public.reelbrain_reap_expired_dm_jobs(batch_size integer default 100)
returns integer language sql volatile security invoker set search_path = ''
as $$
  with changed as (
    update public.reelbrain_dm_jobs j set status='dead_letter',
      last_error=coalesce(last_error,'maximum retries exhausted after expired lease'),
      lease_token=null,lease_until=null,updated_at=now()
    where j.id in (select id from public.reelbrain_dm_jobs
        where status='leased' and lease_until<now() and attempts>=max_attempts
        order by lease_until,id for update skip locked
        limit least(greatest(coalesce(batch_size,100),1),500))
    returning j.id
  ) select count(*)::integer from changed;
$$;
revoke all on function public.reelbrain_reap_expired_dm_jobs(integer) from public,anon,authenticated;
grant execute on function public.reelbrain_reap_expired_dm_jobs(integer) to service_role;
