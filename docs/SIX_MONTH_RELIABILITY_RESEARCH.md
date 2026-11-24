# Six-month, unattended Reelbrain: verified design decisions (2026-11-24)

**User priority:** preserve knowledge first; avoid manual visits for at least one
month, ideally six; free where possible. This page records the difference
between implemented features, vendor promises and guarantees. No frontend work.

## Why Manus (possibly called 'Magnus') appears to understand Instagram Reels

Manus' own video-to-text service describes accepting a video upload or link,
then transcribing speech and using it to summarize content. Its video editor
demonstration and public documentation describe browser/computer operation,
downloads, FFmpeg and visual understanding. It uses its own cloud compute
and credits; it does not publish an open API that grants other apps a universal
right to read Instagram media. Its Instagram Professional connector targets
own-account publishing and insights rather than arbitrary third-party Reel
download. There is no basis to claim a magical no-extraction mechanism.
Reading a public caption or an indexed article and reasoning about it is
different from independently observing video frames or listening to audio.

Verified references:
- https://manus.im/tools/video-to-text
- https://www.manus.im/connectors/instagram
- https://manus.im/blog/introducing-video-editor

## Cost-first, reliable quality architecture

1. **Always:** keep signed Instagram DM URL, creator, verbatim caption, English
   structured claims, timestamps, independent links and ingest health in the
   dedicated Supabase database. **The Reel URL itself must never vanish.**
2. **On new URL:** scheduled GitHub worker checks the durable queue every five
   minutes, drains up to four claims serially, with DB-controlled backoff.
   No Git commit/reopen required per new Reel. GitHub schedules are not a
   persistent 24/7 process and public repo schedules can be auto-disabled after
   60 days without repo activity.
3. **Public metadata stage:** preserve caption/creator claims immediately
   when independently retrievable, but not as invented audio or video evidence.
4. **URL-first speech stage (optional):** a real hosted Instagram transcription
   API is able to accept a Reel URL directly, transcribe off-platform, and
   return words plus optional timestamps. The GitHub runner need not download
   an MP4. The operator must configure a provider account. This implementation
   uses ScrapeCreators `GET /v2/instagram/media/transcript`, with strict
   identity checks, source provenance, 3 attempts/source, 48-hour error backoff,
   and **no more than two paid/cached reservations per UTC day**. All
   three private config gates are OFF by default; NO calls are made until
   explicit owner approval. Transcript text is indexed by private
   `reelbrain_research.search_reels` together with captions and external
   research, even if the original visual pass is still pending.
5. **Full visuals (only if useful and actually accessible):** video bytes
   must reach an authorized decoder or a provider capable of decoding them.
   Stream/temporary-download; ffmpeg/OCR/optional Qwen3-VL; delete temporary
   local input afterward. Captions, transcript and screenshots are separate
   provenance categories. Multi-slide posts require per-page coverage.
6. **Independently verified research:** follow extracted exact official
   repositories/documentation where possible, with English structured
   summaries and facts labeled as official documentation vs creator claims.
7. **Retention:** keep evidence, timestamps, English knowledge and exact
   source links durably; never store persistent MP4s in PostgreSQL or GitHub.

### URL-first transcription providers researched

- **ScrapeCreators**: documented direct Instagram post/Reel URL, 1 credit
  for default successful short (<=120 s) AI transcript, optional timestamps,
  no speech => null. `allow_long_transcription=true` costs more and is
  explicitly disabled. Provider advertises 100 introductory credits but that
  is promotional, not a perpetual free tier. This project has a configured
  **opt-in adapter only**, NOT an active subscription or successful live call.
  https://docs.scrapecreators.com/v2/instagram/media/transcript/
  https://scrapecreators.com/changelog
- **TranscriptFetch** offers an open-source *agent skill wrapper* but the
  actual speech service is hosted, API-based, not a self-hosted universal
  Instagram transcript model. Adding the skill alone does not eliminate cost
  or credentials.
  https://github.com/TranscriptFetch/instagram-transcript-skill
- **Apify** can provide source metadata/video URLs, with separate paid
  transcript/asset options, but its actors can still fail. Existing optional
  Apify adapter is not enabled. A URL-first transcript provider can minimize
  transfer/storage but speech alone will not capture UI/tutorial steps.
- **Gemini / hosted Qwen** analyze video frames **after** an accessible
  visual source (decoded file, provider asset or supported remote video URI)
  is supplied. Sending an arbitrary Instagram permalink to an LLM does not
  guarantee the service fetched or watched the Reel. Qwen3-VL is an open-weight
  model, not free hosted GPU compute.

### Maintenance comparison — what is actually guaranteed?

| Service | Real unattended caveat | Fit |
|---|---|---|
| Supabase Free | Can pause after ~7 days low activity; 500MB DB quota and no managed automatic daily backups on Free. Internal cron activity is **not** a 6-month uptime SLA. | Existing queue/storage, not permanent guarantee |
| Public GitHub Actions | Scheduled event may delay/drop; automatically disabled after 60 days without repo activity. Standard runners are CPU-only. | Existing bounded extraction, not 6-month guarantee |
| Railway Free | 30-day trial then $1/month resource usage allowance and idle-sleep. A continuously running CPU/Whisper worker can exceed allowance; cannot promise six months free. Railway docs say GPU-compute deployments are not its specialty. | Optional CPU worker with verified budget, not default |
| Railway Hobby | $5/month subscription (resource credit applies), then usage charges. | Possible low-maintenance CPU host if owner chooses payment |
| Cloudflare Workers Free Cron | Cheap scheduling/orchestration; 5 cron triggers on free and CPU/memory budgets prohibit running Qwen3-VL locally. It can invoke a GitHub dispatch API only with a scoped GitHub credential, stored privately. | Good durable external clock **once credential is configured** |
| Hosted video/transcript provider | Domain restrictions, prepaid credits, outages, quotas and model updates remain possible. | Accurate URL-first ASR without GitHub downloading media |
| Hosted Qwen3-VL, Gemini multimodal | Provider billing limits, accessible source visuals, API availability. | Optional advanced *visual* verification, not mandatory ASR |

Authoritative documentation:
- https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows
- https://docs.railway.com/pricing/free-plan
- https://docs.railway.com/pricing/free-trial
- https://docs.railway.com/platform/use-cases
- https://supabase.com/docs/guides/platform/free-project-pausing
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/workers/platform/limits/
- https://github.com/QwenLM/Qwen3-VL

## Operator setup of optional hosted speech (no secrets pasted to chat)

Private GitHub **Actions secret**:
- `REELBRAIN_TRANSCRIPT_API_KEY` from the chosen supported
  ScrapeCreators account, which the user owns.

Repository **Actions variables**, set intentionally only after reviewing
credits/pricing and per-key budget:
- `REELBRAIN_HOSTED_TRANSCRIPT_ENABLED=1`
- `REELBRAIN_HOSTED_TRANSCRIPT_BUDGET_APPROVED=1`

The existing `REELBRAIN_DB_URL` remains unchanged. The DB installs a private
per-Reel transcript attempt ledger plus a UTC-day reservation counter.
Even if the provider returns a caption-like inaccurate speech result, mark it
as `third_party_url_speech_transcript` and do not set
`video_analyzed`/`ocr_analyzed` or complete the media acquisition queue.

**Caution:** 2 reservations/day is a technical cap, not a real-dollar spend
cap: each provider call may have special pricing. Currently
`allow_long_transcription=false`. Configure the vendor's *per-key credit
limit* and monitor billing. Turn the variables OFF to stop future charges.
No provider key or approval was created by this change.

## Six-month reliability acceptance gates (NOT yet met)

- Signed DM intake and reconciliation observed for weeks (not just first run).
- Independent external scheduler remains active at month 2/3/6 even if no
  repository commits. Scoped credentials do not expire before that date.
- Proven accessible source audio/media from at least 20 diverse real Reels,
  including speech-only, on-screen slide/text, carousel and mixed languages.
- True searchable transcript and source links persisted, with exact source
  identity and provenance, no metadata masquerading as video observations.
- Automated dead-letter alerts, capacity monitoring, encrypted backups,
  restore drills, and rate/budget guards demonstrated.
- Usage in free/paid provider quotas measured and accounted monthly.
- Actual media changes remain retryable; all six original Reel jobs currently
  media_pending until video source access is proven.
