# Reelbrain Knowledge Engine

Evidence-first personal Instagram Reel → searchable knowledge pipeline, designed for isolation and auditable source links.

**State:** Phase 8 engineering implementation. This repo is publicly visible; it contains **only source code and synthetic tests**, never private research archives, Reel media, tokens, or database backups. Meta 1:1 webhook is deployed but awaits app/account configuration. Real Insta video extraction is not verified. Website and 24/7 media worker not deployed.

### Architecture

```
Instagram Professional account (1:1 Reel DM)
   ↓ Meta `messages` webhook, SHA-256 HMAC and sender allowlist
Supabase Edge Function: reelbrain-instagram-dm (quick 200/queue write)
   ↓ PostgreSQL reelbrain_dm_jobs: unique URL / leases / retries / dead-letter
Separate authorized OCR/ASR/VLM media worker (NOT deployed)
   ↓ evidence + citations → private `reelbrain_research.reel_*` tables
Private website: /api/search + /api/details  (NOT deployed)
   ├ historical source-index + Reel evidence results
   └ read-only, non-persistent GitHub live features/limitations assessment
```

### Modules

- `reelbrain/instagram_dm.py`: pure safe URL extraction from Meta DM event structures.
- `supabase/functions/reelbrain-instagram-dm/index.ts`: webhook signature/auth, deduplicated URL enqueue; **deployed** to dedicated Supabase project, unconfigured pending Meta credentials.
- `sql/0005*`, `0006*`, `0007*`: new isolated Supabase-only queue and Reel evidence records.
- `reelbrain/durable_worker.py`: optional separately hosted, explicitly authorized media worker. Backlog throttles to small batches. Never starts automatically.
- `reelbrain/remote_reel_writer.py`: transactional source/evidence/resource persistence, not fabricated verification.
- `reelbrain_site/`: very small token-gated search and submit website; no Android app.
- `reelbrain/online_research.py`: non-persistent public GitHub metadata and README lookup; no installations or executable software tests.
- `reelbrain/engine.py`: local three-pass OCR + optional ASR + VLM, with partial-success provenance.

### Quick local checks

```bash
python -m unittest discover -s tests -t .
# optional website, only after own DB and long random owner token configured:
pip install -r requirements-site.txt
uvicorn reelbrain_site.app:app --host 127.0.0.1 --port 8000
```

New dedicated PostgreSQL connection must be provided with server-only environment variable `REELBRAIN_DB_URL`; owner website token with `REELBRAIN_DASHBOARD_TOKEN` (at least 32 chars). No secrets in this repository. The private `reelbrain_research` schema is not granted to anonymous clients. See `docs/PHASE8_STATUS.md` and `supabase/functions/reelbrain-instagram-dm/README.md` before use.

The Meta official messaging API does **not** support Instagram group chats. Creating a new Techies group does not solve this. Use three personal accounts to send Reels to a separately connected Professional account via **one-to-one DM**.

**Reality check:** A 180-second Reel understood at human depth in three seconds is not verified, nor a realistic guaranteed SLA on free compute. 24/7 free and unlimited processing cannot be promised.
