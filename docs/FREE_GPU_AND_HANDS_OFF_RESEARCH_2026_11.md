# Reelbrain: free-first 60-Reel burst / six-month viability audit
**As of 2026-11-24. Research stage; no production GPU/API charges authorized.**
**Scope:** only `khushifridayagent/reelbrain-knowledge-engine`, Supabase
`xlkdzrhzizuftbnitodr`, the dedicated Cloudflare
`reelbrain-resilience-clock`. No frontend or unrelated project modifications.

## Decisive finding

Free hosted **GPU-backed inference does exist**, but this must be distinguished
from a free, permanently running GPU virtual machine or a provider that can
reliably retrieve arbitrary Instagram Reel media. The **upstream Reel-access
blocker remains the single highest-priority failure**. No speech/vision model
(including Manus, Qwen3-VL, Cloudflare Qwen3.8, Gemini, or Whisper) can
honestly describe unheard audio or unseen on-screen text from a permalink
alone unless a trusted tool has accessed the source media or an actual
third-party transcript.

The user may send 0, 3–6, or 50–60 Reels/day. Design **durable elastic queues**,
not a guaranteed fixed requests/day throughput. After an influx, the DB must
retain every source URL, metadata, normalized caption claims, provider outputs,
coverage checks and retry/alert state; jobs may safely backlog within free
quotas. Never discard or relabel incomplete work to meet a speed target.

## Current deployed state — checked live

- GitHub repository: public; GitHub connector has admin/push/read access.
- Supabase dedicated project: live, `reelbrain_dm_jobs` **6 queued**;
  `reelbrain_reel_knowledge` **6 media_pending**, **0 video/audio/OCR verified**,
  `reelbrain_research.reel_observations` **0**.
- Current whole PostgreSQL database: **18,732,723 bytes (~18.7 MB)**.
- Existing GitHub Actions media job: scheduled every five minutes, serial
  DB-lease claims, bounded up to four jobs per execution.
- Dedicated Cloudflare Worker `reelbrain-resilience-clock`: cron
  `*/30 * * * *` VERIFIED, but **no Worker secrets**, so it cannot dispatch
  GitHub until scoped `GITHUB_TOKEN` is privately configured.
- Railway connector works, but returned **zero accessible projects**.
- Already-merged PRs #12 and #13 support optional URL-only hosted speech
  and separate Cloudflare backup scheduling. **Neither is live end-to-end**:
  no hosted transcript API key/budget approval, no original-media access.
- TinyFish provider is **NOT connected as a callable ChatGPT plugin** in
  this conversation. No TinyAgent/TinyBrowser credits were consumed.
  A one-shot research brief is provided separately for when the user connects
  TinyFish; the existing public web and provider docs were researched directly.

## Candidate inference backends — strongest useful discoveries

| Platform / model | Current verified recurring free offer | Real obstacle | Decision |
|---|---|---|---|
| **Cloudflare Workers AI Whisper Large V3 Turbo** | Cloudflare Workers AI 10,000 free neurons/day; documented **46.63 neurons per audio minute** | Must supply actual audio bytes; API/request-size/other free-tier limits still apply | Excellent free-first hosted multilingual ASR *when audio is acquired*. |
| **Cloudflare Workers AI Qwen 3.8 27B** | Hosted vision-language model visible in this user's Cloudflare model catalog; shares 10,000 neurons/day | Needs images/decoded frames; model may change availability/quotas; quality on real dense slides untested | Strong candidate to compare against existing Qwen3-VL adapter for frame-level reasoning; **no GPU VM needed**. |
| **Cloudflare Workers AI Llama 4 Scout** | Hosted vision-capable alternative, visible in same account catalog; same neuron pool | Images/frames needed, not arbitrary Instagram URL; free allocation shared with ASR | Visual fallback only if image tests justify it. |
| **Groq Whisper Large V3 / Turbo** | Published free org limits **7,200 audio seconds/hour and 28,800 audio seconds/day**, plus 2,000 requests/day for these models | Requires real audio file/bytes; account-specific limits may differ | Excellent alternative once video audio is accessible; no GPU host. |
| **Modal Starter (serverless GPU)** | **$30 compute credit/month**, $0 base subscription, scheduled/web functions supported; GPU billed per second, scale-to-zero | Modal account not connected; available credit and billing eligibility need verification; model cold-start, memory and CPU costs | Best *potential* truly free recurring self-hosted Qwen3-VL GPU path for bursts, subject to benchmarking and budgets. |
| **Gemini Flash / Flash-Lite** | Some current models have API free tiers for text/images/audio/video | Specific models/quotas and data use differ by model and region; supported video input needed | Optional benchmark for multimodal scenes, not a magical Instagram permalink reader. |
| **Hugging Face ZeroGPU** | Qualified personal free users may host up to 2 ZeroGPU Spaces; free use **5 GPU minutes/day** | Tight daily quota, queue/cold starts; not a reliable 60-Reel/day service | Prototype and quality benchmark only. |
| **Hugging Face Inference Providers** | Free monthly credits only **$0.10** | Not useful for bulk production | Not recommended as primary inference provider. |
| **Railway Free** | Limited monthly resource allowance; zero Railway projects found | CPU service can exceed allowance; not a guaranteed freely available GPU | Do not spin up Railway for Qwen3-VL now. |
| **GitHub hosted Actions** | Public repo CPU runners, bounded transient jobs | No persistent GPU; schedules may delay/disable after 60d no repo activity | Keep as queue consumer/decoder and orchestrator, not GPU host. |
| **TinyFish Search/Fetch** | TinyFish states **Search and Fetch are free** within request limits; supports JS-rendered pages | May retrieve Instagram captions but not verified original audio/frames | Good for caption + cited external-source discovery, not guaranteed transcripts. |
| **TinyFish Agent/Browser** | Signup wallet credits, then metered by step/session | Not permanently free; no connected TinyFish API here | Use scarce trial credits for one deep benchmark, not per-Reel 60/day processing. |
| **ScrapeCreators URL transcript** | URL-in, speech transcript-out via documented provider; trial credits not perpetual | API key and usage credits required; current worker cap only **2 provider calls/day** | Good quality fallback on blocked media, not sufficient for 50–60/day without funded/approved capacity. |
| **Apify Reel scraper** | Public metadata/video URL acquisition; transcript or downloaded-video add-ons may cost extra | May still get 403/429; paid actors; owner key absent | Optional acquisition benchmark with strict spend cap, not base dependency. |

Sources:
- Cloudflare pricing/neuron totals:
  https://developers.cloudflare.com/workers-ai/platform/pricing/
- Cloudflare actual Qwen3.8 27B vision:
  https://developers.cloudflare.com/workers-ai/models/qwen3.8-27b/
- Cloudflare Whisper:
  https://developers.cloudflare.com/workers-ai/models/whisper-large-v3-turbo/
- Cloudflare image/model restrictions:
  https://developers.cloudflare.com/changelog/post/2026-07-28-models-require-workers-paid/
- Groq published free speech limits:
  https://console.groq.com/docs/rate-limits
- Modal $30 recurring credit / pricing:
  https://modal.com/pricing
- HF ZeroGPU quotas:
  https://huggingface.co/docs/hub/spaces-zerogpu
- HF Inference Provider credits:
  https://huggingface.co/docs/inference-providers/pricing
- Gemini per-model free pricing:
  https://ai.google.dev/gemini-api/docs/pricing
- TinyFish:
  https://www.tinyfish.ai/pricing
  https://www.tinyfish.ai/blog/search-and-fetch-are-now-free-for-every-agent-everywhere

## Throughput planning — don't misinterpret input length as GPU runtime

Assume worst-sample 60 Reels in one day, **two minutes of speech each**:
**120 source-audio minutes/day**. Cloudflare Whisper Turbo at 46.63
neurons/minute consumes a theoretical **5,596 neurons**. This would fit
under **10,000 neurons/day** if Whisper is the ONLY or main AI consumer
and request-size/real-world free limits also permit it. Remaining budget
for VLM, external requests and retries is about 4,404 neurons. An ASR-only
minute allowance is NOT an original Instagram retrieval allowance, and
neuron rates can change. Groq's published free 480 audio minutes/day
would also cover this *audio-only* illustration, if the account can
actually provide the bytes and obey minute/second rate caps.

For Modal, illustrative GPU time based on an L4 model rate of
$0.000222/second: the $30 recurring monthly credit would buy a gross
~37.5 GPU-hours/month **before CPU, memory, cold-start and storage costs**.
At 60 seconds GPU time per Reel that is up to ~2,250 Reels/month **gross**;
at 180 seconds GPU time per Reel it is only ~750 **gross**. Those times
are assumptions, not Qwen benchmarks. Since arrival volume varies,
budget-aware deferral and nightly catch-up are more important than
promising no backlog.

No free provider offers an independently verified guarantee of
unlimited 60-Reel/day, full-frame, dense-OCR, speech-plus-visual processing
for six months with zero human maintenance.

## Reliability principles that protect actual knowledge

- **On first receipt**, persist original permalink, sender-safe message
  receipt, canonical media identifier and an immutable timestamp in Supabase.
  No new Git commit is needed per Reel. Do not treat incoming DM as media.
- **Fast metadata pass**: exact caption, creator and content claim labels,
  plus independent web research for named tools, books, GitHub repositories.
  Store extracted claims in English; preserve exact source-language quotes.
- **Speech pass**: prefer free audio-ASR with actual audio bytes; if Instagram
  blocks acquisition, use a URL-first hosted provider only with owner approval.
  Preserve transcript text, language, timestamps and provider provenance.
- **Visual pass**: sample ALL distinct slide/image states, detect short-lived
  onscreen commands and URLs, OCR dense images at multiple scales/languages,
  use Cloudflare Qwen3.8 vision or Modal-hosted Qwen3-VL only on selected
  hard scenes if running with a verified free allocation.
- **Evidence quality**: source quotes and timestamps, exact URLs,
  OCR/ASR/VLM agreement, confidence and contradictory-claim records;
  no VLM-generated URL promoted to fact without a source observation.
- **Completion gate**: a transcript-only or caption-only record may be
  searchable but cannot claim *full video completed*. Do not delete
  original temporary media until all required passes finish and writes
  commit; then delete it. Permanent video storage need not be enabled.
- **No forgotten source**: maintain a searchable source record even if
  upstream media is deleted, blocked or later removed. When text is
  missing, show an explicit coverage gap; never manufacture missing data.
- **Scale handling**: FIFO/priority queue, retries with exponential
  backoff and dead-letter rescue, provider circuit breaker after repeated
  403/429, daily free budget ledger, per-Reel idempotency, and alerts
  on stuck backlog. A 60-Reel day can catch up across future days without
  dropping records.
- **Durability**: 2 separate backup destinations (not original videos),
  encrypted periodic exports and restore tests. R2 has **10 GB-month**
  free included object storage, but operations and policies still have
  limits. A live Supabase DB is *not* its own backup.
- **60-day inactivity**: new Reels alone do not count as GitHub repository
  commits; GitHub public schedules can turn off after 60 days without
  repo activity. Dedicated Cloudflare clock is deployed but **inert**
  until a fine-grained GitHub Actions token is stored in that Worker's
  private secrets. Token expiry still needs monitoring.
- **Supabase**: Free projects may pause with low activity; ordinary
  steady incoming DMs reduce this likelihood but do not create a
  six-month uptime SLA.

## Prioritized 20-Reel acceptance benchmark (required before picking a model)

Run at least 20 genuinely accessible sources:
- 5 spoken tutorial Reels across Hindi/English,
- 5 dense-overlay tutorials including short visible URLs/commands,
- 5 carousel posts, some mixed images/videos (4–20 pages),
- 5 complex/multi-speaker/fast-cut Reels.

Score each source on: media accessibility, caption accuracy, ASR WER,
slide recall, on-screen URL recall, claim citation precision, hallucinations,
knowledge usefulness, wall-clock latency, GPU seconds, free-neuron burn,
retry recovery, total permanent bytes, and exact future search match.
Require manual ground truth review on an initial small batch.
No platform can be declared 'best' on names/benchmarks alone.

## Required one-time connections/configuration (secrets never in chat)

1. Already connected in this ChatGPT conversation: GitHub,
   Supabase, Cloudflare, Railway. No need for a forced 'Allow once'
   prompt; normal tools can request confirmation when a sensitive action
   actually requires it. Railway currently has **no dedicated project**.
2. Connect **TinyFish** in Settings → Plugins if offered, or configure
   its official MCP endpoint from TinyFish's site in a supported MCP
   client. This conversation has **no TinyFish callable tool**; we did
   not spend its credits. A consolidated prompt is in
   `docs/TINYFISH_ONE_SHOT_AUDIT_PROMPT.md`.
3. **Preferred initial free ASR/vision benchmark**: Cloudflare Workers
   AI already appears in this connected account's model catalog as
   `@cf/openai/whisper-large-v3-turbo`,
   `@cf/qwen/qwen3.8-27b`, and
   `@cf/meta/llama-4-scout-17b-16e-instruct`.
   For GitHub-to-Cloudflare REST requests, create a restricted
   Cloudflare AI-scoped API token and save it as a GitHub Actions
   secret (not a DB variable). Actual free-tier invocation and media
   access must still be verified in a bounded test before activation.
4. **Modal GPU proof-of-concept**: If the $30/month recurring Starter
   allowance is genuinely available on the owner's account, connect
   Modal or supply a user-controlled deployed function URL/key to
   GitHub secrets. No account or credential exists here yet. Use
   workspace hard budgets and scale-to-zero; avoid a 24/7 idle GPU.
5. **Cloudflare GitHub fallback**: add fine-grained, 6+-month lifetime
   PAT in the dedicated clock's **secret** named `GITHUB_TOKEN`,
   scoped to this repository Actions Read+Write. Do not reuse
   or overwrite unrelated Worker credentials.
6. **URL-first hosted speech option**: the existing code specifically
   expects a **ScrapeCreators** key saved as GitHub repository secret
   `REELBRAIN_TRANSCRIPT_API_KEY`; two separate approval variables
   must be intentionally enabled. The current 2/day capped implementation
   is inappropriate for regular 50–60/day usage until the owner approves
   sustainable pricing/budget and a deliberately revised cap.
7. **R2 optional backup**: only after measuring actual full-Reel evidence
   sizes and defining encryption/restore strategy; do NOT buy blob storage
   merely to keep transient original Instagram video files.
8. **Keep frontend and See More Details deferred.**

## Honest next-step gate

This research is complete enough to choose **a benchmark**, not enough
to mark the six pending Reels as processed or promise six months unattended.
The best initial cost-saving combination worth actually testing is:
**Existing Supabase + GitHub + Cloudflare Workers AI Whisper Turbo and
Qwen3.8 Vision (shared Free quota)**, with source extraction supplied
by legitimately accessible Instagram bytes or a verified hosted provider.
Modal's recurring $30/month free GPU credit is a compelling second
benchmark for truly open-weight Qwen3-VL, **if account eligibility and
cold-start operating cost check out**.
