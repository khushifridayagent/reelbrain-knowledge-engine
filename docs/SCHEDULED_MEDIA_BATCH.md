# Scheduled media batch — opt-in GitHub Actions fallback

This is a *best-effort*, no-dedicated-VM batch runner for the isolated Reelbrain project. The existing Supabase five-minute coordinator still only coordinates; this workflow is the first separately scheduled executor. The workflow **does not run by default** and does not make the pipeline 24/7, free-unlimited, or able to download all Instagram Reels.

## Configure securely

1. In this repository's **Settings → Secrets and variables → Actions → Secrets**, create `REELBRAIN_DB_URL` with the **dedicated** `xlkdzrhzizuftbnitodr` PostgreSQL connection URI. Do not paste it into the repository, workflow YAML, Issues, Actions logs, or chat. Use an appropriately restricted database role where feasible. Verify DNS, IPv4/pooler connectivity, and the actual role's privileges.
2. In **Settings → Secrets and variables → Actions → Variables**, create `REELBRAIN_WORKER_ENABLED` = `1`. Leave it unset or `0` to disable all jobs. The URL must belong to the dedicated project: `checked_config()` rejects other projects.
3. Optionally trigger the **Reelbrain scheduled media batch** workflow manually from the Actions tab, or let its scheduled runs proceed twice an hour. GitHub may delay or disable scheduled workflows and puts limits on minutes; no per-minute processing or 24/7 SLA is implied.
4. Review the Actions run results, the isolated `reelbrain_dm_jobs` queue and `reelbrain_reel_knowledge` stage/flags. Failure categories are recorded without raw downloader output. Do not treat caption/metadata as proof that speech/video was analyzed.

## Boundaries and limitations

- Processes **at most one Reel per invocation**, 20-minute job timeout. The database uses transactional claims and bounded retry/dead-letter. Keep concurrent external workers off until lease expiry and batch timing have been tested.
- Uses public, no-cookie `yt-dlp` only, with OCR via ffmpeg/Tesseract; may fail due to login restriction, rate limits, format changes or source removal. Does not bypass private Instagram content.
- No paid Apify and no Groq/Gemini by default. `REELBRAIN_EXTERNAL_MODEL_UPLOAD_ALLOWED=0`: cloud audio transcription and model-based visual understanding are not enabled; OCR may be the only audiovisual stage on available videos.
- Ephemeral runner deletes temporary downloaded media after each run. A run is not a persistent VM and may be unsuitable for heavier processing or large bursts.
- This is **not** a replacement for a private always-on worker when reliable and timely handling is required. Repository stays PUBLIC but private knowledge never belongs in GitHub artifacts.

## Acceptance before claiming real completion

1. A scheduled or manual run succeeds with the dedicated secret, while the source Reel is publicly accessible.
2. A job moves from `queued` to `processed` or `partial` **only after** actual media acquisition and proven evidence persistence. On failure it remains retryable or dead-lettered, not falsely marked understood.
3. Run 20 diverse real, approved samples and inspect timestamped OCR/audio/video evidence. Test duplicate deliveries, failures, cost caps and reliability separately.
