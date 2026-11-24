# Reelbrain production hand-off: transcript API, Cloudflare and evidence fidelity
Last audited: 2026-11-24. This is **not** a claim that the six queued Reels have been fully processed.

## Cloudflare external clock is now configured

The user added a **classic GitHub PAT** to the existing dedicated Cloudflare Worker
secret named `GITHUB_TOKEN`, which was verified through Cloudflare's
**secret metadata API** without reading or printing the credential. The
`*/5 * * * *` Cron Trigger is now deployed and verified (changed 2026-11-24 11:20 UTC; propagation can take up to 15 minutes).

Important: the uploaded TinyFish report assumes a *different implementation*
(`GITHUB_DISPATCH_TOKEN` + `repository_dispatch` and Contents:Write).
**Do NOT blindly apply it to our existing code**.
`deploy/reelbrain-cloudflare-clock.mjs` currently uses:
- Cloudflare secret: `GITHUB_TOKEN`
- GitHub REST `GET /actions/workflows/reelbrain-media-batch.yml`
- `PUT /enable` if disabled
- `POST /dispatches` with `{"ref":"main"}`, on `workflow_dispatch`.
- A GitHub token authorized to perform workflow dispatch and enable.
  A fine-grained PAT scoped to this repository with Actions Read/Write is
  preferable to classic PAT for least privilege. A classic PAT may work if it
  grants relevant `workflow`/`repo` permissions, but has broader exposure.
- Token existence is **not proof** that the dispatch endpoint returns 204.
  Verify a new run with event `workflow_dispatch` *after* the next half-hour.
- Rotate token before its actual expiry; a 6-month guarantee requires
  Cloudflare and GitHub permissions/limits to remain in force.

## What is actually missing for source audiovisual knowledge

Six Reels are still queued and six knowledge rows `media_pending`;
metadata and exact creator captions are saved but no genuine video/ASR/OCR
observations are stored. GitHub media downloading continues to encounter
Instagram anonymous datacenter 403/429, so **the model is not the primary
blocker**. Cloudflare Whisper and Qwen Vision cannot analyze source data they
never receive. Do not claim verified speech from a creator caption.

## New choice of URL-first hosted spoken transcripts (PR #15)

A private, credit-capped TranscriptFetch v2 client can now coexist with the
original ScrapeCreators adapter. It:
- POSTs an exact canonical Instagram Reel URL to
  `https://transcriptfetch.com/api/v2/transcripts/video`.
- Sets `mode='audio'` (the **actual spoken track**, not written caption)
  and `timestamps=true`.
- Verifies provider platform='instagram', exact Reel shortcode match,
  source='audio', transcript size and timestamp segment bounds.
- Handles HTTP 200 inline completion and 202 + `asr_...` `job_id`.
- Persists `job_id` privately and polls a *fixed* provider endpoint later.
  Async polls do **not** reserve a new billable start call.
- Stores third-party speech in `provider_audio_transcript` as a separate
  evidence category, with original captions and visual/OCR source claims
  never overwritten. Pending full-media OCR/vision queue stays pending.
- Attempts to recover stale claimed transactions and acknowledges errors.
  A shared maximum of **two new starts per UTC day** remains the default,
  so it is a bounded proof-of-concept. With a provider plan/credits already
  purchased and the explicit budget approval flag, set GitHub repository
  variable `REELBRAIN_HOSTED_TRANSCRIPT_DAILY_LIMIT=60` (1–120 permitted).
  This allows up to 60 separately queued sources/day with no auto-upgrade
  or automatic paid subscription. **Provider credits charged are not
  guaranteed equal to API starts** (long videos may cost more).
  Set a hard provider-account spend cap independently.

**Actual credentials required to enable a live call** (do not paste into chat):

GitHub → `khushifridayagent/reelbrain-knowledge-engine` →
Settings → Secrets and variables → Actions:

1. Repository **secret**: `TRANSCRIPTFETCH_API_KEY` from
   https://transcriptfetch.com/app
2. Repository **variables**:
   - `REELBRAIN_HOSTED_TRANSCRIPT_PROVIDER=transcriptfetch`
   - `REELBRAIN_HOSTED_TRANSCRIPT_ENABLED=1`
   - `REELBRAIN_HOSTED_TRANSCRIPT_BUDGET_APPROVED=1`
3. Existing private `REELBRAIN_DB_URL` stays unchanged, is already
   successfully used by the GitHub worker, and MUST NOT be replaced with
   the TinyFish suggested `SUPABASE_SERVICE_ROLE_KEY`.
4. Available private SQL migration:
   `sql/0028_hosted_async_transcripts.sql`.
5. The optional provider stage runs from `.github/workflows/reelbrain-media-batch.yml`
   after the initial lightweight PostgreSQL health check.

Official up-to-date docs:
- https://transcriptfetch.com/docs/instagram/transcript
- https://transcriptfetch.com/docs/jobs/status
- https://transcriptfetch.com/help/ai-transcription
- https://transcriptfetch.com/help/first-transcript

**There is no TranscriptFetch secret configured by ChatGPT, no paid plan
purchased and no real Reel was silently sent to the provider.**

## Follow-on free/advanced AI configurations

These models were verified by Cloudflare account catalog:
- `@cf/openai/whisper-large-v3-turbo` — ASR only after real audio bytes
- `@cf/qwen/qwen3.8-27b` — visual interpretation only after valid frames
- `@cf/meta/llama-4-scout-17b-16e-instruct` — alternate visual model

Workers AI has a shared 10,000-neuron-per-UTC-day Free allocation, not
unlimited free full-video extraction. The GitHub worker already contains
local faster-whisper CPU, FFmpeg, Hindi/English OCR and an optional Qwen3-VL
OpenAI-compatible visual adapter; a Cloudflare API token/model endpoint must
be configured and **tested against real media** before calling it active.
The user has not yet provided those inference credentials.

### GitHub configuration for Cloudflare Qwen 3.8 image understanding

For existing local FFmpeg-extracted visual frames, the code now supports
Cloudflare's official OpenAI-compatible endpoint with the established
`reelbrain/qwen_vl.py` adapter:
`https://api.cloudflare.com/client/v4/accounts/<account_id>/ai/v1`.

GitHub repository secret: `CLOUDFLARE_AI_API_TOKEN` — create a restricted
Cloudflare Workers AI API token in the owner's Cloudflare dashboard.

GitHub repository variables:
- `CLOUDFLARE_ACCOUNT_ID` — 32-character Cloudflare account ID.
- `REELBRAIN_CLOUDFLARE_VISION_ENABLED=1`
- `REELBRAIN_EXTERNAL_MODEL_UPLOAD_ALLOWED=1`

The worker chooses `@cf/qwen/qwen3.8-27b` when these are all configured.
This is a hosted multimodal **image** model, not a video-permalink retriever.
It samples up to eight frames from actually downloaded assets. Default OFF;
there is no guaranteed free-neuron headroom for 50–60 visual-heavy sources.
Read daily Workers AI usage before enabling and limit call frequency.
Official source:
https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/

The deep research report from TinyFish is useful as a source of candidate
providers, but its suggested paths `src/processors/visual_inference.py`
and `.github/workflows/media-batch.yml` do NOT match the actual code.
Actual paths are `reelbrain/qwen_vl.py` and
`.github/workflows/reelbrain-media-batch.yml`.
Do not commit incorrect paths or replace correct secrets.

## Required end-to-end acceptance to claim 'done'

1. Cloudflare dispatch result actually succeeds, token not expiring soon.
2. New DM automatically enqueues without a manual GitHub push.
3. At least one of the six real sources gives **audio transcript with
   timestamps**, persists and is retrievable by exact topic keyword.
4. Actual Reel frames, OCR and links from visual overlays are analyzed;
   image carousels preserve all pages, including small, fast texts.
5. At least 20 diverse actual sources pass a quality gold set; no
   caption-only rows counted as audiovisual success.
6. Burst 50–60 sources/day remains lossless under quotas and backoff.
7. Backup/restore and capacity alarms prove database durability beyond
   one sole Supabase Free instance. Cloudflare R2 may be configured later,
   only with a scoped key, encryption and tested recovery.
8. No frontend or 'See More Details' until backend quality is proven.

A six-month fully unattended, free, high-quality SLA is **not yet proved**.
