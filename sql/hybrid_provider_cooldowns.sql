-- Private, bounded per-provider cooldown; no media, credential or raw response storage.
create table if not exists reelbrain_research.hybrid_provider_cooldowns (
 provider text primary key check (provider in ('gemini_vision','groq_vision','cloudflare_vision')),
 blocked_until timestamptz not null,
 updated_at timestamptz not null default now()
);
alter table reelbrain_research.hybrid_provider_cooldowns enable row level security;
revoke all on reelbrain_research.hybrid_provider_cooldowns from public, anon, authenticated;
