# Phase 9 — Reelbrain autonomous queue coordination and real-media worker code

**Evidence cutoff: November 24, 2026 (Asia/Kolkata).** Never confuse successfully received Reel URLs with analyzed audiovisual content.

## Actual live acceptance result

- Official Meta one-to-one `ig_reel` webhook, restricted to **3 specifically approved senders** and checked HMAC, delivered `HTTP 200` to `reelbrain-instagram-dm` Edge Function v11.
- A genuine Instagram Reel was saved as private `reelbrain_dm_jobs` Job 5, URL `https://www.instagram.com/reel/DaQLc80PIBU/`, status `queued`, zero processing attempts at the time of audit.
- A public caption, creator, topic and independently documented research were persisted in `reelbrain_reel_knowledge`, with actual video/audio/OCR flags FALSE. The source has `processing_stage=media_pending` after the coordinator tick.
- A five-minute `pg_cron` job now dispatches an authenticated Edge coordinator to repair expired leases, preserve the Reel queue, create evidence-accurate pending placeholders and write heartbeat rows. Live invocation returned `HTTP 200` with `queued_or_leased=1`, `full_media_worker_started=false`.
- A separate native Meta Graph reconciler rechecks **one approved sender per tick** every 5 minutes (three sender cycle ~15 min). It stores canonical Reel URLs and per-message receipts if Graph supplies them; some native attachments are omitted from Graph history and need webhook delivery. One approved account live reconciliation returned `HTTP 200`; a previous 3-account single run exceeded the 40-second timeout and was replaced by staggered per-account calls.
- No paid Apify, Groq, Gemini or unidentified scraping credentials were accessed or charged during this release.

## Code finished but not actually hosted

- `reelbrain/public_media.py`: best-effort public Reel media downloader via yt-dlp, without cookies, with HTTPS host validation, byte-size and time budgets, and an actual MP4 receipt check.
- `reelbrain/durable_worker.py`: preflight explicit rights/consent, selects either free public extraction or opt-in paid Apify; lease/ack/retry semantics remain in PostgreSQL. Download attempts cannot be assumed to succeed for every Instagram Reel.
- `reelbrain/engine.py`: existing OCR, optional Groq ASR, optional Gemini visual inference, timestamped observations, unsupported-link validation. `reelbrain/media_evidence_summary.py` and updated `remote_reel_writer.py` persist actual media observations while distinguishing model inference.
- `deploy/Dockerfile.media-worker` and `requirements-worker.txt`: isolated container with Tesseract Hindi/English, ffmpeg, OpenCV, yt-dlp, psycopg, opt-in Gemini SDK.
- Node parsing/coordinator/reconciler and Python pure-unit regression tests; public repository contains only code and synthetic test fixtures.

## Missing external dependencies to achieve 24/7 FULL audiovisual extraction

1. A **separate authorized compute host** (e.g., a new Railway instance, VPS or always-on cloud runner) that executes the Dockerfile/worker continuously. The Railway connector returned **zero projects** for this user during setup, so no cloud worker was created or verified. Supabase Edge+Cron by itself cannot host this ffmpeg/OpenCV pipeline.
2. The **isolated** Reelbrain PostgreSQL URI `REELBRAIN_DB_URL` in the host's sealed secrets. Never share or commit the DB URI.
3. Owner-controlled public video download permission (`REELBRAIN_SOURCE_RIGHTS_CONFIRMED=1`, `REELBRAIN_MEDIA_ACQUISITION=yt_dlp_public`, `REELBRAIN_ALLOW_PUBLIC_REEL_DOWNLOAD=1`) and an empirical test on accessible, public real Reels. Some Reels may be blocked by Instagram; alternate authorized provider may incur charges.
4. If audio/video AI is required, configure permitted Groq/Gemini keys and opt-in remote uploads, and test accuracy/quotas. OCR works locally after a real video is accessible.
5. Production golden dataset: 20–100 real diverse Reels, provenance/URL precision and recall, burst testing, rates, alerting, 7-day uptime, license and security review.

Until these are verified **do not** mark source as fully understood, **do not** say every DM is guaranteed captured, **do not** mark the media worker 24/7 active. Existing queue rows remain available and safe for an independently hosted worker.