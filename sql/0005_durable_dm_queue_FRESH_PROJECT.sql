-- New Reelbrain Supabase project ONLY. Never run on unrelated databases.
-- Dedicated append/lease/ack queue. Shared media not downloaded by this migration.
create table if not exists public.reelbrain_dm_jobs (
 id bigint generated always as identity primary key,
 source_url text not null unique,
 inbound_event_id text not null,
 sender_digest text not null check(length(sender_digest)=64),
 status text not null default 'queued' check (status in ('queued','leased','processed','partial','dead_letter')),
 attempts integer not null default 0 check(attempts>=0),
 max_attempts integer not null default 5 check(max_attempts between 1 and 12),
 available_at timestamptz not null default now(),
 lease_token uuid, lease_until timestamptz,
 source_id text, result_summary jsonb, last_error text,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 check ((status='leased')=(lease_token is not null and lease_until is not null))
);
create index if not exists reelbrain_dm_work_idx on public.reelbrain_dm_jobs(status,available_at,id);
create index if not exists reelbrain_dm_lease_idx on public.reelbrain_dm_jobs(lease_until) where status='leased';
alter table public.reelbrain_dm_jobs enable row level security;
revoke all on public.reelbrain_dm_jobs from public, anon, authenticated;
revoke all on sequence public.reelbrain_dm_jobs_id_seq from public, anon, authenticated;
grant select,insert,update on public.reelbrain_dm_jobs to service_role;
grant usage,select on sequence public.reelbrain_dm_jobs_id_seq to service_role;

-- All functions are invoker, not definer. Only authenticated server-side service_role can execute.
create or replace function public.reelbrain_claim_dm_jobs(batch_size integer default 2,lease_seconds integer default 180)
returns setof public.reelbrain_dm_jobs
language sql volatile security invoker set search_path=''
as $$
  with selected as (
    select id from public.reelbrain_dm_jobs
    where ((status='queued' and available_at<=now())
      or (status='leased' and lease_until<now()))
      and attempts<max_attempts
    order by available_at,id for update skip locked
    limit least(greatest(coalesce(batch_size,2),1),10)
  )
  update public.reelbrain_dm_jobs j
  set status='leased',lease_token=gen_random_uuid(),
      lease_until=now()+make_interval(secs=>least(greatest(coalesce(lease_seconds,180),30),900)),
      attempts=attempts+1,updated_at=now()
  from selected where j.id=selected.id
  returning j.*;
$$;
create or replace function public.reelbrain_finish_dm_job(job_id bigint,token uuid,finished_status text,summary jsonb default '{}'::jsonb)
returns boolean
language sql volatile security invoker set search_path=''
as $$
 with changed as (
   update public.reelbrain_dm_jobs set status=finished_status,
     result_summary=left(summary::text,16000)::jsonb,
     lease_token=null,lease_until=null,updated_at=now(),last_error=null
   where id=job_id and status='leased' and lease_token=token and lease_until>now()
     and finished_status in ('processed','partial')
   returning 1
 ) select exists(select 1 from changed);
$$;
create or replace function public.reelbrain_fail_dm_job(job_id bigint,token uuid,reason text)
returns boolean
language sql volatile security invoker set search_path=''
as $$
 with changed as (
   update public.reelbrain_dm_jobs
   set status=case when attempts>=max_attempts then 'dead_letter' else 'queued' end,
     available_at=now() + make_interval(secs=>least(3600, power(2,least(10,attempts))::integer * 10)),
     lease_token=null, lease_until=null,updated_at=now(),last_error=left(coalesce(reason,'unknown failure'),400)
   where id=job_id and status='leased' and lease_token=token
   returning 1
 ) select exists(select 1 from changed);
$$;
revoke all on function public.reelbrain_claim_dm_jobs(integer,integer) from public,anon,authenticated;
revoke all on function public.reelbrain_finish_dm_job(bigint,uuid,text,jsonb) from public,anon,authenticated;
revoke all on function public.reelbrain_fail_dm_job(bigint,uuid,text) from public,anon,authenticated;
grant execute on function public.reelbrain_claim_dm_jobs(integer,integer) to service_role;
grant execute on function public.reelbrain_finish_dm_job(bigint,uuid,text,jsonb) to service_role;
grant execute on function public.reelbrain_fail_dm_job(bigint,uuid,text) to service_role;
