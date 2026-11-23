# Scheduled media batch — opt-in GitHub Actions fallback

This is a *best-effort*, no-dedicated-VM batch runner for the isolated Reelbrain project. The existing Supabase five-minute coordinator still only coordinates; this workflow is the first separately scheduled executor. The workflow runs on its schedule once merged to `main`, but performs media processing **only when its dedicated GitHub Actions DB secret exists**. It does not make the pipeline 24/7, free-unlimited, or able to download all Instagram Reels.

## Configure securely

1. In **this exact GitHub repository's** **Settings → Secrets and variables → Actions → Repository secrets**, check for `REELBRAIN_DB_URL`. If already present and complete, you **do not need to add a separate database password secret**. The PostgreSQL connection URI itself must include a valid database password (URL-encoded if it contains special URI characters) unless your specific authenticated connection method supplies it elsewhere. Supabase dashboard Connection strings may display a `[YOUR-PASSWORD]` placeholder; that is not a real password. Prefer the session pooler URI for hosted IPv4-only runners. Do not paste credentials into the repository, workflow YAML, Issues, Actions logs, or chat. Use an appropriately restricted role where feasible. A Supabase Edge Function secret or secret in another GitHub repo does **not** count as a secret in this repository. Verify DNS, pooler connectivity, and DB role privileges.
2. **No GitHub repository variable is required to start.** Once `REELBRAIN_DB_URL` exists, the next scheduled run (or the one-time `push` run after this workflow change reaches `main`) attempts the worker. The optional `REELBRAIN_WORKER_ENABLED=0` variable explicitly pauses the worker. An unset variable or `1` enables it. The URL must belong to the dedicated project: `checked_config()` rejects other projects.
3. Check the **Reelbrain scheduled media batch** workflow in the GitHub Actions tab. It triggers once on a workflow-file change pushed to `main`, then twice an hour by schedule, and can also be manually dispatched. If the secret is not present, the job logs a clear warning and skips all expensive install and processing steps. GitHub may delay or disable scheduled workflows and imposes usage limits; no per-minute processing or 24/7 SLA is implied.
4. Review the Actions run results, the isolated `reelbrain_dm_jobs` queue and `reelbrain_reel_knowledge` stage/flags. Failure categories are recorded without raw downloader output. Do not treat caption/metadata as proof that speech/video was analyzed.

## Boundaries and limitations

- Processes **at most one Reel per invocation**, 14-minute job timeout (below the 15-minute database job lease). The database uses transactional claims and bounded retry/dead-letter. Keep concurrent external workers off until lease expiry and batch timing have been tested.
- Uses public, no-cookie `yt-dlp` only, with OCR via ffmpeg/Tesseract; may fail due to login restriction, rate limits, format changes or source removal. Does not bypass private Instagram content.
- No paid Apify and no Groq/Gemini by default. `REELBRAIN_EXTERNAL_MODEL_UPLOAD_ALLOWED=0`: cloud audio transcription and model-based visual understanding are not enabled; OCR may be the only audiovisual stage on available videos.
- Ephemeral runner deletes temporary downloaded media after each run. A run is not a persistent VM and may be unsuitable for heavier processing or large bursts.
- This is **not** a replacement for a private always-on worker when reliable and timely handling is required. Repository stays PUBLIC but private knowledge never belongs in GitHub artifacts.

## Acceptance before claiming real completion

1. A scheduled or manual run succeeds with the dedicated secret, while the source Reel is publicly accessible.
2. A job moves from `queued` to `processed` or `partial` **only after** actual media acquisition and proven evidence persistence. On failure it remains retryable or dead-lettered, not falsely marked understood.
3. Run 20 diverse real, approved samples and inspect timestamped OCR/audio/video evidence. Test duplicate deliveries, failures, cost caps and reliability separately.

## Security note: database password

Do **not** post your database password or connection URI in chat. Do **not** set `REELBRAIN_DB_URL` as a public Actions variable. The one GitHub Actions **secret** holds the complete `postgresql://...` connection URI. If its password portion was omitted, replace that same secret privately with the full valid URI from your dedicated Supabase project's **Connect → Session pooler** UI. This workflow never prints the secret value. The configured secret name can be checked in GitHub Settings, but its stored contents cannot be read back.
