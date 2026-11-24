# Reelbrain Knowledge Engine

## LIVE VERIFIED — 24 Nov 2026, 16:40 IST

**Cloudflare→GitHub workflow_dispatch:** ✅ verified, no new PAT needed.
**Supabase connection / URL-first TranscriptFetch:** ✅ live and storing real
third-party speech transcripts. Initial two successful URLs were the
Google Compute Engine and Paperclip Reels; retrieved successfully by
`reelbrain_research.search_reels('dashboard shows every task',12)` with
`verification_level=third_party_url_speech_transcript`. First-party
video frames, OCR and complete visual coverage remain **NOT VERIFIED**.

**Elastic queue:** for the selected `transcriptfetch` provider, the old
`REELBRAIN_HOSTED_TRANSCRIPT_DAILY_LIMIT=60` is now ignored as a daily
work cap. It remains as a legacy safety setting only for ScrapeCreators.
Every new incoming Reel stays durably queued; each recurring GitHub tick
takes a small bounded chunk (up to two hosted ASR starts per tick). Before
every new TranscriptFetch start the worker calls the provider's FREE
`GET /api/v2/me` balance endpoint. On zero balance it pauses without
claiming/dropping sources; if balance *actually* increases later it
automatically resumes. HTTP 402 and 429 do not consume finite source
failure attempts. GitHub Actions' best-effort scheduling can be delayed,
and backlog catch-up may span multiple days. Do not confuse a per-tick
timeout bound with an arbitrary daily input limit.

**Important credit reality:** a starter pack of 50 free credits is not a
guarantee of free processing forever. The provider's current web pages
disagree about free-credit renewal, so do not assume that a balance
returns every month. This system resumes on observed credit replenishment,
not an invented date; if the credits never refill, the backlog remains
safely paused until the account is funded or another proven free
acquisition route exists. No subscription or overage was purchased by
this project.

**Cloudflare vision:** the user's existing
`REELBRAIN_CLOUDFLARE_VISION_ENABLED=1` together with
`CLOUDFLARE_AI_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` activates the
image-only Qwen 3.8 adapter **without** requiring generic Groq/Gemini
model-upload permission. Images still require real video/frame access.
No frontend or See More Details deployment has occurred.

**Production fixes:** PR #18 fixed PostgreSQL JSONB parameter typing
after a first genuine provider result failed persistence. PR #19 added
elastic credit-driven processing and applied the isolated migration
`sql/0031_elastic_transcript_credit_backlog.sql`; PR #20 fixed the
provider-specific Cloudflare vision opt-in. CI passed for each.
This is the CURRENT implementation; older historical phase notes below
describe earlier snapshots and must not be mistaken for current state.


## 2026-11-24 — Cloudflare token confirmed; URL-first ASR and hosted vision adapters

**Cloudflare**: The dedicated `reelbrain-resilience-clock` Worker now has a
private `GITHUB_TOKEN` secret and its half-hour Cron Trigger is deployed.
The original Worker uses `workflow_dispatch` (not
`repository_dispatch`), so **do not follow the differently named token
or workflow path proposed in the uploaded third-party research report**.
A secret being present is not proof of successful GitHub dispatch: verify an
actual GitHub Actions run with event `workflow_dispatch`.

**Backend changes**: the optional TranscriptFetch v2 provider handles
`POST /api/v2/transcripts/video` for URL-first *spoken audio* extraction,
with 200 completion or 202 persisted `asr_...` job, free polling, exact
shortcode checks, and separately stored/labelled third-party transcripts.
The existing ScrapeCreators provider is unchanged and can still be selected.
An opt-in Cloudflare Workers AI hosted
`@cf/qwen/qwen3.8-27b` visual backend now connects to the existing frame
sampler with the official OpenAI-compatible Cloudflare API URL. No model
bytes or secrets are committed. These adapters are **OFF by default** and
will not contact providers unless owner-managed API tokens and explicit
GitHub Actions variables are set. This is not an Instagram media access fix.

**See [Provider setup and operations](docs/TRANSCRIPT_PROVIDER_DEPLOYMENT_2026_11.md).**
Six original Reels are still pending true media/OCR/ASR verification.
No frontend, paid provider or unapproved storage integration is deployed.

## 2026-11-24 — free GPU and 2–6 month unattended research

**Read first:** [Free GPU / hands-off architecture audit](docs/FREE_GPU_AND_HANDS_OFF_RESEARCH_2026_11.md), [One-shot TinyFish brief](docs/TINYFISH_ONE_SHOT_AUDIT_PROMPT.md).

**New research finding:** Cloudflare Workers AI (available in the connected account) hosts
`@cf/qwen/qwen3.8-27b` **vision** and
`@cf/openai/whisper-large-v3-turbo` **speech recognition**.
The Workers AI Free allowance is **10,000 Neurons per day shared by all
models**. This is a *candidate inference backend*, **not** a deployed
end-to-end pipeline or a native arbitrary-Instagram-Reel URL transcriber.
Audio bytes and decoded video frames must be made accessible to the service.
At 60 x 2-minute Reels/day, Whisper-only usage is theoretically about
5,596 Neurons before retries/vision; actual provider limits and access
conditions require a real benchmark.

**Alternative GPU:** Modal advertises **$30/month recurring compute credit**
on Starter with scale-to-zero GPU containers; real Qwen3-VL throughput, account
eligibility, request admission and total GPU/CPU/memory charges must be tested
before deployment. **Railway's Free plan is not a free always-on Qwen GPU.**
TinyFish Search/Fetch are documented free; Agent/Browser calls use limited
credits. TinyFish is **not currently connected to this conversation**; its
full consolidated research brief has been committed without using those credits.

**Operational reality:** all **six** original Reel jobs are still queued,
creator/caption metadata is saved, **0/6** have independently verified
video/ASR/OCR observations. The separate Cloudflare backup cron exists but
needs a fine-grained GitHub Actions token in its own private secret to work.
URL-first paid transcript provider and hosted Qwen3-VL remain opt-in/off.
Do not mistake GitHub green CI or saved captions for full video understanding.

**No frontend, See More Details UI, provider spending, or unrelated projects
were changed by this research phase.**


Evidence-first personal Instagram Reel → searchable knowledge pipeline, designed for isolation and auditable source links.

**State (24 November 2026):** Phase 9 autonomous **DM intake and queue coordination deployed** on isolated Supabase; one real direct `ig_reel` received and persisted. Exactly three owner-approved sender IDs are stored only in the private Supabase allowlist. Postgres cron rechecks queue every five minutes, and official Graph reconciliation checks each sender roughly every 15 minutes. Public Reel caption/metadata and distinct official-topic research can be stored in `reelbrain_reel_knowledge`. **Actual full-video OCR/ASR/VLM worker is implemented in Python but NOT hosted or verified on real media.** Website is NOT hosted. The repository is PUBLIC and contains code and synthetic tests only, no secrets or private media.

### Phase 11: autonomous queue drain (November 2026)

The backend now uses the durable Supabase DM queue with a **5-minute,
best-effort GitHub Actions poll**. Each scheduled runner can drain up to
**four eligible Reels sequentially**, then exits; new submissions are picked
up automatically on a later poll without adding commits or opening ChatGPT.
The main bottleneck for the six initial Reels is Instagram anonymous media
access, **not** Supabase queuing or persistent video storage. The optional
Apify actor integration is **not enabled**, and Qwen3-VL still requires an
actual remote GPU endpoint. Full multimedia success is **not yet proven**:
six items remain pending as of the most recent audit.

**See `docs/AUTONOMOUS_QUEUE_AND_STORAGE.md`** for flow, credentials,
selection of optional third-party services, measured DB usage (18 MB), and
storage projections. Original media is transient and deleted after each run.
Frontend and See More Details remain deferred.

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
