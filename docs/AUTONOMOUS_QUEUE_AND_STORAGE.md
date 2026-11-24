# Reelbrain backend: automatic queue processing, acquisition choices and storage

This document reflects the isolated backend architecture, **not** a guarantee
that every submitted Instagram Reel is accessible. No frontend has been created.

## How a new Reel becomes research

1. An Instagram Professional account receives an approved **1:1** share via the
   official Meta messaging webhook. The dedicated Supabase Edge Function
   verifies signature and sender, then atomically persists the message receipt
   and canonical Reel URL in `public.reelbrain_dm_jobs`. It does not send media
   files to GitHub or commit anything to the public repository.
2. The durable Postgres queue owns pending jobs, idempotency, leases, access
   backoff and recovery. Metadata/coordinator cron continues every 5 minutes.
3. The GitHub Actions `reelbrain-media-batch.yml` polls the queue **every 5
   minutes** (GitHub may delay or occasionally disable scheduled runs). If no
   eligible job, the job skips FFmpeg/Tesseract/AI model installation. If jobs
   exist, it drains **up to 4 serial claims** with a bounded run budget. Once
   a Reel is saved, the next scheduled poll will pick it up without reopening
   the chat, changing code or manually pushing new Reel references.
4. The worker first tries anonymous public yt-dlp/gallery-dl. A user-supplied
   Instagram-only session cookie can be used from a **private GitHub secret**
   for authorized viewing. A 403/429/access failure is deferred rather than
   being falsely marked processed.
5. For acquired media, transient video/image files are created on the
   ephemeral GitHub runner, analyzed with local source OCR/Whisper, and
   deleted on success or failure when the `TemporaryDirectory` exits.
   Evidence and citations are persisted to the dedicated Supabase database,
   with independently researched docs separated from source claims.
6. A success requires actual media evidence, not merely caption metadata or
   a successful scheduled job. Track status in `reelbrain_dm_jobs`,
   `reelbrain_reel_knowledge`, and `reelbrain_research.reel_*`.

**New queue events do not require a Git commit.** Event-to-GitHub webhook
`workflow_dispatch`/repository_dispatch is technically possible, but requires
a scoped GitHub App/PAT credential in Supabase Vault. Until that specific secret
exists, authenticated every-five-minute polling is simpler and works without
adding another vulnerable credential. This is autonomous *periodic* processing,
not a permanently running compute node or a strict latency SLA.

## Media acquisition and hosted model choices

| Stage | Default | Optional (not enabled by this PR) |
|---|---|---|
| Instagram URL/creator/caption | Signed DM; public metadata if truly verified | Paid actor for unavailable public metadata |
| Reel video source | yt-dlp, gallery-dl; private owner session secret supported | Apify `apify/instagram-reel-scraper` with token and explicit approval |
| Audio | Local multilingual faster-whisper CPU on transient extracted WAV | Paid remote Whisper ASR after explicit owner upload opt-in |
| Visual / slide text | Adaptive ffmpeg frames + Hindi/English Tesseract; 20-slide carousel | Qwen3-VL with a real external GPU inference endpoint |
| Knowledge | Metadata and independent documentation separate from source observations | Extra provider transcript must be labeled by provenance |

Apify's official Reel Actor supports direct Reel URLs in the `username`
array and may return `url: .../p/<shortcode>/` for an input
`.../reel/<shortcode>/`. The adapter verifies the *shortcode*, not the URL
alias. The actor reports caption and original video URL by default, but
**transcript and downloaded-video add-ons are separately billed**; both are
explicitly disabled in the adapter by default. The actor is a promising
fallback, not a guaranteed retrieval method. No paid actor or GPU endpoint
was automatically activated.

Optional Apify setup (only if the owner explicitly decides to incur charges):
- Repository **secret** `APIFY_API_TOKEN` (never paste it in chat);
- Repository variables `REELBRAIN_MEDIA_ACQUISITION=apify`,
  `REELBRAIN_PAID_PROVIDER_APPROVED=1`, and
  `REELBRAIN_SOURCE_RIGHTS_CONFIRMED=1` after checking actual rights/terms.
- To use hosted Qwen3-VL/Groq/Gemini models, separately configure their
  actual API endpoint/keys and `REELBRAIN_EXTERNAL_MODEL_UPLOAD_ALLOWED=1`.

These variables are deliberately **unset** by this PR. A provider's actor
costs can change: always inspect the live pricing tab and set a provider-level
spend limit if enabling it. Unless configured, the **free-first** path remains
the only worker.

The official Meta webhook can supply an `ig_reel` title, URL and video ID;
those are **not automatically the raw downloadable video**. Meta API media
access scopes generally do not allow fetching arbitrary third-party Reels
solely because the Reel permalink was shared.

## Database and years of storage: measured and modelled

Measured on **2026-11-24** for Supabase project `xlkdzrhzizuftbnitodr`:
- PostgreSQL database size: **18,626,227 bytes (~18 MB)** across the *entire*
  database, including index/extension/other existing tables.
- `reelbrain_reel_knowledge`: six metadata-only rows totaling **7,352 bytes**
  of row-level storage (~1,225 bytes/row), plus table/index overhead.
- At measurement time: **0 fully audiovisual-processed Reels** and zero
  `reelbrain_research.reel_observations`. The six current rows are **not**
  representative of the eventual detailed extraction size.
- Supabase Free advertised database quota **500 MB/project** and file storage
  **1 GB/project**, and low-activity projects can be paused. Limits change.
  Internal cron activity does not guarantee immunity from pause policies.

Planning scenarios, not storage guarantees, assuming **10 new Reels/day**,
all media discarded, and **50 KB or 150 KB effective PostgreSQL growth per
fully processed Reel** (all indexed evidence, transcript, OCR, references):

| Scenario | Reels/year | Estimated growth/year | Remaining 482 MB, idealized lifetime |
|---|---:|---:|---:|
| 50 KB / Reel | 3,650 | ~183 MB | ~2.6 years |
| 150 KB / Reel | 3,650 | ~548 MB | ~0.9 years |

These exclude varying table/index overhead, TOAST compression, WAL and
vacuum/bloat, schema changes, backups, temporary files, and external
metadata. There is **no measured full-Reel average yet**, so projecting
an exact lifetime is not possible.

**Recommended durable policy:** Store English summaries and structured
knowledge, timestamped source quotations/links, evidence hashes and
small metadata in Postgres. Keep *no long-term original videos*. Only
consider object/blob storage for encrypted, versioned backups and cold
archive exports once real evidence volume is measured; a blob bucket is
not required to run the current extraction worker. Monitor database
size at 50/70/85% thresholds and deploy an automated backup before
approaching the Free quota. A free plan is not a forever-storage SLA.

## Acceptance checks before calling it done

- Newly shared Reel becomes a unique Supabase queued row automatically.
- New job picked up on next real GitHub schedule, no manual dispatch required.
- Two available jobs are processed serially during one run if within time
  budget; access failure on one should not starve the next.
- No media or credentials are committed to the public GitHub repo.
- Every fully processed Reel has source-linked video/OCR/ASR evidence and
  successful persisted Postgres transaction, not just creator caption.
- The six original IDs remain pending until actually proven.
- Confirmed live success with at least one public Reel and a multi-slide
  image post, not only synthetic mock tests.
