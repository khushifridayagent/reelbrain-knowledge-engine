# Reelbrain Knowledge Engine

Evidence-first personal Instagram Reel → searchable knowledge pipeline, designed for isolation and auditable source links.

**State (24 November 2026):** Phase 9 autonomous **DM intake and queue coordination deployed** on isolated Supabase; one real direct `ig_reel` received and persisted. Exactly three owner-approved sender IDs are stored only in the private Supabase allowlist. Postgres cron rechecks queue every five minutes, and official Graph reconciliation checks each sender roughly every 15 minutes. Public Reel caption/metadata and distinct official-topic research can be stored in `reelbrain_reel_knowledge`. **Actual full-video OCR/ASR/VLM worker is implemented in Python but NOT hosted or verified on real media.** Website is NOT hosted. The repository is PUBLIC and contains code and synthetic tests only, no secrets or private media.

### Phase 10 backend status — 24 November 2026

- **Deployed:** dedicated Supabase DM intake, durable job queue, metadata coordinator (5-min cron), 3-sender reconciling and a GitHub Actions **10-minute scheduled batch runner** that has successfully connected to the isolated Reelbrain PostgreSQL database. No additional DB password/variable needs to be entered.
- **Implemented:** a second public gallery-dl acquisition adapter, 20-asset Instagram carousel/post ingest with per-slide evidence, English/Hindi OCR and dense-text improvements, local multilingual `faster-whisper` ASR, optional hosted Qwen3-VL frame-understanding adapter and structured evidence persistence. Source parsing and synthetic unit tests passed GitHub CI. See `docs/MODEL_PIPELINE_AND_ACCEPTANCE.md`.
- **Live failure remains:** as of the last observed run, Instagram's anonymous GitHub-hosted acquisition failed through both yt-dlp and gallery-dl; six sources remained `media_pending` with **zero proven audiovisual extraction**. This is a **media-access blocker**, not a database credential problem. Jobs remain queued/retryable with bounded dead-letter instead of being falsely marked processed.
- **Not deployed:** GPU serving Qwen3-VL, paid provider calls, a permanent 24/7 VM, and the deliberately deferred private website. GitHub Actions checks periodically; it is not a continuous always-on compute host or guaranteed zero-backlog SLA.
- **Operations:** inspect `.github/workflows/reelbrain-media-batch.yml`, GitHub Actions failures and `public.reelbrain_dm_jobs`; no secrets or user media belong in this PUBLIC repository.

### Architecture

```
Instagram Professional account (1:1 Reel DM)
   ↓ Meta `messages` webhook, SHA-256 HMAC and sender allowlist
Supabase Edge Function: reelbrain-instagram-dm (quick 200/queue write)
   ↓ PostgreSQL reelbrain_dm_jobs: unique URL / leases / retries / dead-letter
Supabase cron coordinator (live) + separate authorized OCR/ASR/VLM worker (code ready, host NOT deployed)
   ↓ evidence + citations → private `reelbrain_research.reel_*` tables
Private website: /api/search + /api/details  (NOT deployed)
   ├ historical source-index + Reel evidence results
   └ read-only, non-persistent GitHub live features/limitations assessment
```

### Modules

- `reelbrain/instagram_dm.py`: pure safe URL extraction from Meta DM event structures.
- `supabase/functions/reelbrain-instagram-dm/index.ts`: webhook signature/auth, deduplicated URL enqueue; **deployed** to dedicated Supabase project, unconfigured pending Meta credentials.
- `sql/0005*`, `0006*`, `0007*`: new isolated Supabase-only queue and Reel evidence records.
- `reelbrain/durable_worker.py`: externally hosted Python media worker using optional public yt-dlp or explicitly approved paid Apify acquisition, ffmpeg/Tesseract OCR, opt-in Groq ASR and Gemini VLM. Code ready; **host and credentials still required**, not running 24/7. `reelbrain/public_media.py` and `reelbrain/media_evidence_summary.py` implement safe public access and evidence provenance.
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

New dedicated PostgreSQL connection must be provided with server-only environment variable `REELBRAIN_DB_URL`; owner website token with `REELBRAIN_DASHBOARD_TOKEN` (at least 32 chars). No secrets in this repository. The private `reelbrain_research` schema is not granted to anonymous clients. See `docs/PHASE8_STATUS.md`, **`docs/PHASE9_IMPLEMENTATION_AND_GAPS.md`**, **`docs/MEDIA_WORKER_DEPLOYMENT.md`** and `supabase/functions/reelbrain-instagram-dm/README.md` before use.

The Meta official messaging API does **not** support Instagram group chats. Creating a new Techies group does not solve this. Use three personal accounts to send Reels to a separately connected Professional account via **one-to-one DM**.

**Reality check:** A 180-second Reel understood at human depth in three seconds is not verified, nor a realistic guaranteed SLA on free compute. 24/7 free and unlimited processing cannot be promised.

### Live autonomous control plane (isolated Supabase only)

- `supabase/functions/reelbrain-knowledge-coordinator/` and SQL migrations `0010` + `0012`: one-shot authenticated cron every five minutes; recovers expired leases, ensures every saved Reel has a `media_pending` knowledge row, stores a heartbeat, **does not consume media jobs without an authorized external host**.
- `supabase/functions/reelbrain-dm-reconciler/` and SQL `0011` + `0012`: backup official Graph lookup for three approved 1:1 senders, staggered so each is reviewed every ~15 minutes; Graph does **not** always expose direct Reel attachment URLs, so webhook remains primary.
- `deploy/Dockerfile.media-worker`, `requirements-worker.txt`: build the separately hosted multimedia worker with ffmpeg, Tesseract, OpenCV, psycopg, yt-dlp and opt-in external ASR/VLM. For deployment and permissions see `docs/MEDIA_WORKER_DEPLOYMENT.md`.

**Do not interpret this controller as full media processing**: zero actual videos have passed the 20-Reel quality gold set. The existing live sample remains `queued` in the media queue with `processing_stage=media_pending` until a separate worker accesses video bytes and produces audited observations.
