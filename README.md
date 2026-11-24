# Reelbrain Knowledge Engine

### REAL META GRAPH DIAGNOSTIC — 2026-11-24 (prioritize this over older setup notes)

The owner **has already configured** GitHub Secret `REELBRAIN_META_GRAPH_TOKEN`
and repository variables `REELBRAIN_META_IG_USER_ID` and
`REELBRAIN_META_BUSINESS_DISCOVERY_ENABLED=1`. They do **not** need to
repeat those steps. A real GitHub Actions canary tested the protected token
without logging its value:

- **Meta Graph User Token currently valid** (`GET /me` success).
- Configured numeric ID rejected on `GET /{id}?fields=id,username`
  with Graph **code 100**: likely an App/Page ID rather than an accessible
  Professional IG user ID, but code 100 alone cannot prove which.
- Official `GET /me/accounts` returned **0 accessible Facebook Pages**
  and **0 linked Instagram Professional account IDs**. Safe self-resolution
  from a single linked Page could therefore not run.
- Actual token scopes (safe boolean audit):
  `instagram_basic=YES`, `pages_show_list=YES`,
  `pages_read_engagement=YES`,
  **`instagram_manage_insights=NO`**.
- These requirements are external Meta account permissions/linkage.
  Replacing OCR/Qwen models, changing the GitHub scheduler, or saving
  an expired short-lived token in GitHub cannot grant them automatically.
- Verified read-only probes: [#45402208996](https://github.com/khushifridayagent/reelbrain-knowledge-engine/actions/runs/45402208996),
  [#45403093805](https://github.com/khushifridayagent/reelbrain-knowledge-engine/actions/runs/45403093805),
  [#45403770932](https://github.com/khushifridayagent/reelbrain-knowledge-engine/actions/runs/45403770932).
  All failed *accurately*, without printing raw bearer keys or signed URLs.
- PRs #36–#38 (CI green) provide safe diagnostic categories, one-linked-IG
  ID recovery in the production media worker, and non-sensitive Page/
  permission visibility counts. Backend changes are already merged.

**The exact remaining owner action:** Confirm Instagram account type is
Business/Creator and **link it to a Facebook Page** accessible to the token
owner in Meta Business Suite (inactive posting is OK, deactivated/inaccessible
Page is not). In the **same** Meta App `reel` under Graph API Explorer,
authorize `instagram_basic`, `instagram_manage_insights`,
`pages_read_engagement`, `pages_show_list` (Page role granted through
Business Manager may need `ads_read` or `ads_management`).
Regenerate a properly scoped token; treat Graph API Explorer tokens as
**short-lived**, not a six-month credential. A supported long-lived or
renewable authentication arrangement is needed for hands-off operation.
Update the existing GitHub protected token with the newly authorized one.

When Meta rate limits clear, query:
`GET /me/accounts?fields=id,name,instagram_business_account{id,username}`
and use **`instagram_business_account.id`**, never App ID or Page ID,
for `REELBRAIN_META_IG_USER_ID`. Re-run
Actions → `Reelbrain Meta Graph access canary (permissions audit)`
→ Run workflow. Even with correct account permissions, Meta may omit the
original `media_url` for copyright/licensed audio or if the owner has
disabled Reel downloads. Do not mark such Reels visually completed.

**Current knowledge coverage:** 6/6 first-party received Reel URLs have
actual third-party spoken transcripts saved and retrievable; **0/6 actual
original frame/OCR/QR visual evidence**. All 6 media tasks remain in the
durable retry queue. Existing Cloudflare → GitHub best-effort 5-minute
scheduling is working and has **not been disabled** for this audit.

Official reference: https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/business_discovery


### 2026-11-24 verified visual-access status (read this first)

**Real tests:** Cloudflare-hosted Qwen image reasoning worked on a
synthetic workflow diagram and identified the login modal/thumbnail
on real Instagram public/embed pages. Two *actual queued Reels* still
failed full MP4 acquisition with the most recent official yt-dlp nightly
on GitHub Actions (0/2). **6/6 have hosted speech transcripts, 0/6 have
original video frames, screen OCR or QR evidence.** Neither Qwen nor
a static Instagram poster is proof of video understanding.

[**Exact evidence, production code fixes, and the one-time optional
official Meta Business Discovery setup**](docs/INSTAGRAM_VISUAL_UNBLOCK_VERIFIED_2026_11.md).
A read-only Meta Graph professional-creator source-media fallback is now
implemented, tested and **OFF until the owner's own appropriately scoped
Graph token and professional IG user ID are configured**; no provider
purchase or frontend deployment has been made.


## Priority: on-screen Reel knowledge, screenshots, QR links, carousel pages (24 Nov 2026)

**This is the highest-priority missing output.** Saving spoken audio is NOT
equivalent to understanding the video. Store literal onscreen text/commands,
decoded QR payloads, exact page/timestamp source links, workflow arrows,
configuration steps, inputs/outputs, underlying business logic, and English
knowledge explanations. A song or instrumental background is not knowledge;
do not infer visually shown details from a speech transcript or caption.

**Now implemented and synthetic-CI-tested (PRs #27–#30):**
- `reelbrain/qr_evidence.py`: deterministic offline QR decoder for real photo
  pixels and video frames (5Hz, bounded), with exact timestamps and URL
  candidates. It is independent of VLM hallucinations; no commenting or
  creator DM is necessary if a QR is actually visible in the media.
- `reelbrain/media.py` and `reelbrain/engine.py`: per-image Tesseract
  + QR on a **1–20 page** carousel, preserved `slide:01..20` evidence
  locators, real video 10Hz adaptive OCR + 5Hz QR, original source evidence
  stored apart from inference.
- `reelbrain/qwen_vl.py`: Cloudflare-hosted Qwen vision now inspects
  scene-aware sampled video frames in up to 4 batches of 8, not just
  8 uniformly selected frames total. Every visual explanation includes
  selected sample timestamps. It interprets diagram arrows, workflows,
  code/screenshots, tools, settings, prerequisites, and teaching steps.
- Quota on page #N **must not discard earlier page descriptions**; partial
  model successes and local OCR/QR persist and queue retries remain possible.
  If a video has more distinct scenes than the sampling budget, status
  stays **partial**; do not falsely mark complete visual coverage.
- Private `reelbrain_research.search_reels` now indexes **every stored
  on-screen OCR, decoded QR, first-party ASR and AI visual-model explanation**
  directly with its actual `slide:NN` or `MM:SS` locator.
  Distinct verification levels include `onscreen_qr_source`,
  `onscreen_ocr_source` and `visual_model_inference`.
- Screenshot-based tests and the 20-page QR fixture passed isolated CI.
  NO private image/video content is stored in the public GitHub repository.

**Actual live verification (dedicated Supabase project
`xlkdzrhzizuftbnitodr`):** 6/6 original Reels currently have real
third-party **spoken** transcripts, but **0/6 have true acquired frames,
screen OCR or decoded QR**. All six original first-party media jobs remain
in the queue; no fake visual description was inserted. Public Instagram
access through anonymous GitHub-hosted downloads is the blocker.
Cloudflare Qwen **cannot open arbitrary Instagram Reel pages by itself**:
the model requires actual images/decoded frames. A verified accessible
source-media bridge or authorized externally accessible media is still
required before the visual engine can run on these six Reels.

**Do not confuse two different Qwen lines:** self-hostable `Qwen3-VL`
supports video OCR and temporal understanding, while the connected
Cloudflare model `@cf/qwen/qwen3.8-27b` is a hosted **image+text** vision
model. The Cloudflare API currently receives sampled frames, not a raw
Reel permalink. Neither generative model replaces exact deterministic QR
decoding or high-recall OCR. They complement each other.

**Cost correction:** The often-repeated **~40–45 neurons** figure applies
to Cloudflare **Whisper audio model usage per audio minute** (Whisper Large
V3 Turbo: **46.63 neurons per audio minute**), NOT a fixed Qwen whole-video
price. Qwen3.8 bills per text/image input tokens and generated output tokens;
scene and image size affect consumption. Workers AI Free shares **10,000
neurons/day**, reset at **00:00 UTC**, across ALL models. Quota exhaustion
must preserve backlog; it is not a promise of unlimited free full-video
inference or a two-to-six-month no-intervention SLA.

Original references:
- https://github.com/QwenLM/Qwen3-VL
- https://developers.cloudflare.com/workers-ai/models/qwen3.8-27b/
- https://developers.cloudflare.com/workers-ai/platform/pricing/
- https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/


## LIVE VERIFIED — 24 Nov 2026, 16:40 IST

**Cloudflare→GitHub workflow_dispatch:** ✅ verified, no new PAT needed.
**Supabase connection / URL-first TranscriptFetch:** ✅ live with all **6 of 6** original
Reels now storing actual third-party audio speech, each with timestamped segments.
Initial two were Google Compute Engine and Paperclip; the subsequent four
came from real GitHub Actions run #45384096213 (four provider starts and four
verified speech records). Retrieved successfully by
`reelbrain_research.search_reels('dashboard shows every task',12)` with
`verification_level=third_party_url_speech_transcript`. First-party
video frames, OCR and complete visual coverage remain **NOT VERIFIED**.

**Audio milestone:** 6/6 hosted speech; **visual/OCR milestone:** 0/6 original frames analyzed, so six original media jobs intentionally remain queued for retry. Provider transcription is not proof of visual content.

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
private `GITHUB_TOKEN` secret and its verified 5-minute Cron Trigger (`*/5 * * * *`) are deployed. The existing secret triggered real `workflow_dispatch` runs, and no repository token changes are required.
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
