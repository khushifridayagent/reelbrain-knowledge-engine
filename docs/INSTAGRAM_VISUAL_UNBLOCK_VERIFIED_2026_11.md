# Reelbrain: real Instagram frame-access and Cloudflare Qwen verification

**Last live audit:** 2026-11-24, dedicated repo
`khushifridayagent/reelbrain-knowledge-engine` and Supabase
`xlkdzrhzizuftbnitodr` only. Frontend intentionally deferred.

## What was ACTUALLY executed — NOT a plan

- **Qwen visual inference on connected Cloudflare account:** real
  `@cf/qwen/qwen3.8-27b` API call with an ORIGINAL synthetic PNG
  workflow diagram, `INPUT → FILTER → OUTPUT` and a conditional instruction.
  The model's reasoning recognized the labels/order correctly, but this
  first short-token test returned null final text (`finish_reason=length`);
  usage **55.69 Neurons**. A real account screenshot experiment using
  `reasoning_effort=low` produced a visible complete answer.
- **Public Instagram page screenshot + Qwen:** Cloudflare Browser
  Rendering actually loaded
  `https://www.instagram.com/reel/DgGHCjZIZtW/`.
  Qwen identified the Instagram **Sign up / Log in modal** and black,
  unloaded video behind it; screenshot + Qwen cost **155.33 Neurons**.
- **Official public Reel `/embed/` URL:** Browser Rendering screenshot
  + Qwen saw a **static poster/image**, not verified moving video
  playback or decodable video bytes. This experiment cost **280.68
  Neurons**. A separate dynamic Playwright browser check found a
  `<video>` DOM node with `videoWidth=0`, `readyState=0`
  and no MP4 network request. That is not the original video.
- **Most recent official yt-dlp nightly** (2026.11.23.232705.dev0)
  installed successfully on a clean GitHub-hosted Ubuntu runner. A
  REAL source-byte canary tried two queued public Reel shortcodes
  `DgGHCjZIZtW` and `DaQLc80PIBU`; **0/2 MP4 downloaded**.
  The tested workflow correctly FAILED (red), with URLs and media not
  saved or exposed. GitHub Actions run
  https://github.com/khushifridayagent/reelbrain-knowledge-engine/actions/runs/45392648702

These results directly refute the claim that switching Qwen models,
or updating yt-dlp, automatically fixes Instagram original media access.

## Backend work deployed despite that external access obstacle

- QR decoding of source image/actual video frames, independent from
  Qwen hallucination; actual screenshots, exact strings and timestamped
  observation remain first-party only when actual media is accessible.
- Up to 20 ordered carousel slides, bilingual OCR/QR, source citations.
- Up to 32 scene-aware Qwen image samples over 4 bounded calls; individual
  frames/time and workflow descriptions stored as *model inference*.
- Preserve prior slides, OCR and QR when free quota runs out; missing
  scene coverage marks partial status, never fake completed.
- `reelbrain_research.search_reels` indexes exact frame OCR, QR,
  diagram descriptions and spoken transcripts in separate provenance tiers.
- PR #34 updated Cloudflare Qwen to low reasoning and structured JSON
  output mode, specifically because a real test had no final content with
  a tiny completion limit. This does not make it zero-neuron or free
  for unlimited input volume.
- **PR #33 introduced an OFF-by-default official Meta Business Discovery
  fallback** into the existing public-media worker. If the public
  yt-dlp/gallery path fails, the fallback can read another PUBLIC
  professional creator's media using the owner's authorized Meta Graph
  token and own professional account ID, then match EXACT source
  creator+shortcode and fetch Meta's real `media_url` into a temporary
  private directory. All carousel children must be returned; missing
  original/video bytes stop the job (no false visual success).

## Official Meta fallback: one-time setup (NOT configured yet)

This mode is opt-in. It does not require Apify or a permanent GPU server.
The professional account and app must satisfy the necessary Instagram
Graph permissions, app review and business discovery access.

GitHub → Repository Settings → Secrets and variables → Actions:

1. Repository **secret** `REELBRAIN_META_GRAPH_TOKEN`:
   a legitimately authorized Facebook/Instagram Graph **access token**
   associated with the owner's Meta app & professional IG account.
   **Do not use** `META_APP_SECRET` or webhook
   `META_VERIFY_TOKEN` here; never paste token into chat/repo code.
2. Repository **variable** `REELBRAIN_META_IG_USER_ID`:
   **numeric Instagram professional User ID** of the owner's own account.
   Not the username, App ID, Page ID or Project Ref.
3. Repository **variable** `REELBRAIN_META_BUSINESS_DISCOVERY_ENABLED=1`.

These values are NOT presently in the repository's known secrets/vars.
Existing IG DM webhook configuration in Supabase is a different
permission surface; its verifying a callback does not prove Graph
Business Discovery authorization.

When configured, the **existing** GitHub worker (Cloudflare Cron
dispatch every 5 min plus GitHub schedule) attempts:

`Public Reel/Post URL → yt-dlp/gallery → if blocked and Meta enabled:
   find creator handle from Supabase → official Meta Business Discovery →
   match source_shortcode → obtain original media_url/ordered carousel
   children → validate and temporarily fetch CDN bytes →
   QR + OCR + Qwen Vision → structured searchable Supabase evidence →
   delete temporary media`

The official method cannot access arbitrary personal/private accounts.
Even for public professional accounts, Meta can intentionally omit
`media_url` for licensed audio, copyright or disabled Reel downloads.
This absence must **not** be bypassed or treated as a media success.
See official Meta media field reference:
https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/v21.0/

## What is not yet achieved

- **Actual 6 original Reel frame results: 0/6**. All 6 hosted
  spoken transcripts have been saved; 6 original-media jobs remain
  queued/deferred because media has not been acquired.
- The new Meta optional path is code-tested, **not** live-tested on
  those six: no Meta Business Discovery token configured.
- The three Qwen experiments are genuine Cloudflare account inference,
  but they do **NOT** establish full real-Reel QR/OCR recall or free 6-month
  capacity. Exact Qwen cost depends on image/input/output tokens and
  thinking effort; Whisper's **46.63 Neurons/audio minute** is unrelated.
  The Free Neuron pool is 10,000/day shared across inference models.
- Cloudflare + GitHub scheduling runs best-effort with no permanent
  always-on GPU; quota, provider access and token expiry prevent
  guaranteeing a six-month 100% zero-maintenance service.

Next acceptance gate: After Meta fallback is authorized, show **at
least one** of the original six sources with actual trusted MP4/image
bytes; prove Qwen/QR/OCR from actual visual frames are saved with
timestamps and recoverable via `search_reels`, then investigate the
other five and a real 20-page carousel. Missing original bytes are
an acquisition/provider limitation, not evidence that Qwen cannot
understand real images.
