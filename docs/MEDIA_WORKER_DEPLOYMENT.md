# Reelbrain Media Worker — isolation, deployments, and verified status

Scope: **ONLY** the isolated Reelbrain Knowledge Supabase project `xlkdzrhzizuftbnitodr` and repository `khushifridayagent/reelbrain-knowledge-engine`. Never attach to an unrelated Supabase/Railway project.

## What is already live

1. Meta Instagram `ig_reel` 1:1 messages from three approved accounts are authenticated, stored as private receipts, and their canonical Reel URL is deduplicated in `public.reelbrain_dm_jobs`.
2. `reelbrain-knowledge-coordinator` Edge Function is deployed. Supabase `pg_cron` calls it every five minutes with a one-use, DB-signed, short-lived nonce. It repairs expired leases, flags pending media jobs, and stores a heartbeat in `public.reelbrain_worker_state`.
3. The source knowledge table stores metadata and independent research. Neither a webhook receipt nor the coordinator **downloads video** or **analyzes speech and frames**.

## The actual multimedia processor (separate host)

The Python worker `python -m reelbrain.durable_worker` uses an isolated PostgreSQL connection, lease locks and retry/dead-letter functions. On *real downloaded MP4* it can run:

- **Frame OCR:** local ffmpeg + OpenCV + Tesseract (English/Hindi installation)
- **ASR:** Groq Whisper if owner explicitly enables model upload and configures `GROQ_API_KEY`
- **Video understanding:** Gemini video inference if Google SDK, model and key are configured; results are *model inference*, not verified facts
- **Evidence and citations:** timestamped OCR/speech observed facts, separate VLM inferences, resource URLs only when in evidence, transactional persistence to `reelbrain_research.reel_*` and `public.reelbrain_reel_knowledge`
- **Retries:** PostgreSQL lease/recovery with up to five bounded retries and exponential backoff
- **Deletion:** downloaded Reel media is held in a temporary directory and discarded after processing; no private chat text is stored.

### Source acquisition (explicit opt-in)

Default mode is `apify` (PAID; use only if separately authorized with rate/expense budget). Alternative `yt_dlp_public` attempts to retrieve only public Instagram Reels, without browser cookies; this can fail due to Instagram limitations and **does not bypass private/logged-in content**. Neither method guarantees that every third-party Reel can be downloaded.

### Environment variables (server-side secrets only)

Required for every full worker:

```dotenv
REELBRAIN_DB_URL=<dedicated Reelbrain Knowledge PostgreSQL URI, not an unrelated DB>
REELBRAIN_SOURCE_RIGHTS_CONFIRMED=1
REELBRAIN_MEDIA_ACQUISITION=yt_dlp_public
REELBRAIN_ALLOW_PUBLIC_REEL_DOWNLOAD=1
```

Optional for authorized audiovisual AI:

```dotenv
REELBRAIN_EXTERNAL_MODEL_UPLOAD_ALLOWED=1
GROQ_API_KEY=<your private Groq key>
GROQ_ASR_MODEL=whisper-large-v3-turbo
# For Gemini install google-genai in the Docker image and configure:
GEMINI_API_KEY=<your private Gemini key>
GEMINI_VIDEO_MODEL=<current supported video model verified in your account>
```

If and only if enabling a paid media acquisition provider:

```dotenv
REELBRAIN_MEDIA_ACQUISITION=apify
REELBRAIN_PAID_PROVIDER_APPROVED=1
APIFY_API_TOKEN=<private key>
```

**NEVER** paste database passwords, model keys, access tokens or video bytes into this public repository or chat. On a host set sealed environment variables and cost alerts.

### Container deployment

- Build using `deploy/Dockerfile.media-worker` from **this repository's root**.
- Run **one** replica initially; never use more than one without concurrency/budget testing.
- Supply all secret env vars through your new deployment platform's Secrets UI.
- Keep the worker private: it has **no public HTTP endpoint**. All traffic is outbound.
- Choose a host with enough memory for Python, ffmpeg, OpenCV, and AI uploads; Supabase Edge Functions are not a substitute for this process.
- Cloud hosting is **not yet live** unless you have subsequently supplied and verified a new host. The existing user's Railway connector currently returned no projects at the time of building this feature.

## Acceptance and quality gates

Do not claim full media completion until ALL of these pass on 20 owner-authorized real Reels:
- source media accessible in the chosen provider; actual MP4 receipt
- complete timestamped OCR, ASR and visual understanding without fabricated facts
- original links verified against source OCR/audio/captions
- repeated messages/idempotency, 100-message burst, webhook outage reconciliation
- 7-day autonomous live runs, error recovery and deployment costs under approved budget

Until then, existing metadata-only jobs retain `queued` status and `media_pending` knowledge stage, with `video_analyzed=false` and `audio_transcribed=false`.