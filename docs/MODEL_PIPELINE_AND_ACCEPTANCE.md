# Reelbrain backend: production modalities, model routing and acceptance

**Scope:** only this repository and dedicated Supabase project `xlkdzrhzizuftbnitodr`. The frontend/search website is intentionally deferred. This document describes implemented code versus live-proven processing. No public Instagram URL, even from a Reel DM, guarantees availability of the original video bytes.

## Source → evidence pipeline

1. **Official Instagram DM webhook** saves canonical Reel or post URL in the deduplicated private PostgreSQL queue. The Supabase 5-minute coordinator handles pending states; it does not transcribe or read frames.
2. **GitHub Actions scheduled worker (10-minute cadence)** leases at most one eligible source at a time and uses the existing isolated database secret. This runner is ephemeral, not an always-on GPU worker.
3. **Media acquisition:** for `/reel/`, try yt-dlp then no-cookie gallery-dl. For `/p/`, use gallery-dl to get each image/video in order; reject truncated or invalid media. Both depend on Instagram returning actual public files. No hidden login bypass or false success.
4. **Dense screenshot OCR:** adaptive 10Hz scene-change sampling + URL-focused recheck for video, EXIF correction/upscale and dual Tesseract page-layout modes for photo slides, Hindi + English trained OCR. Source observations retain `MM:SS` or `slide:NN` citations.
5. **Speech-to-text:** CPU-compatible multilingual `faster-whisper` `small` int8 model (local by default after actual video acquisition). If explicitly enabled and a `GROQ_API_KEY` secret exists, choose hosted `whisper-large-v3-turbo` for lower ASR latency instead.
6. **Visual understanding:** Qwen3-VL-8B (optional OpenAI-compatible vLLM/SGLang GPU host; **not** part of a free CPU GitHub Actions runner). Optional Gemini remains supported. Every generated visual description is labeled `model_inference` and cannot validate an alleged tool URL alone.
7. **Knowledge persistence:** structured evidence, exact locators, cited URLs and separate model inferences are committed transactionally to private Reelbrain tables. Missing/blocked acquisition stays retryable or dead-lettered; metadata-only does **not** masquerade as full media knowledge.

## Model tradeoffs

| Modality | Included default | Higher-capability optional option | Hardware/credential |
|---|---|---|---|
| Screenshot and short overlay text | Tesseract English + Hindi, adaptive frame sampling, photo upscale | PaddleOCR-VL-1.5/1.6 or PP-OCRv6 evaluated as a **future** enhancement | Optional external GPU/runtime, not deployed |
| Audio speech | Multilingual faster-whisper `small` CPU/int8 | Groq Whisper large-v3-turbo | Groq API key and explicit remote-model opt-in |
| Video and dense poster reasoning | Source OCR + ASR evidence; no invented generative model result | Qwen3-VL-8B-Instruct via configured `/v1` inference API; Gemini fallback | Separately hosted GPU endpoint and opt-in; not automatically provided by GitHub |
| Structured features / links | Evidence-aligned URL normalization and source citations | Independent read-only GitHub research | Public GitHub network calls; no private cloning |

These are *candidates* for a quality/latency benchmark, not a measured claim that one model is universally best. For a two-minute video, two-minute full comprehension is a **target, not a guarantee**: CPU ASR, densely changing slides and unavailable media can take longer.

## GitHub Actions configuration

- Required existing **repository secret**: `REELBRAIN_DB_URL` containing full connection URI for project `xlkdzrhzizuftbnitodr`. No separate database password variable.
- Local speech runs by default with `REELBRAIN_ENABLE_LOCAL_ASR=1` and `REELBRAIN_LOCAL_ASR_MODEL=small`. The first model download may be slow; subsequent runs can reuse GitHub Actions model cache.
- **Optional**, only if an operator provides a GPU inference service:
  - Repository secret `REELBRAIN_QWEN_VL_BASE_URL=https://YOUR_REAL_GPU_HOST/v1`
  - Repository secret `REELBRAIN_QWEN_VL_API_KEY` if endpoint requires it
  - Optional repository variable `REELBRAIN_QWEN_VL_MODEL=Qwen/Qwen3-VL-8B-Instruct`
  - Repository variable `REELBRAIN_EXTERNAL_MODEL_UPLOAD_ALLOWED=1` to permit external uploads.
  - Optional repository secret `GROQ_API_KEY` for hosted Whisper, or `GEMINI_API_KEY` if using Gemini instead of Qwen.
- These optional secrets and variables do **not** exist automatically; the worker must not claim hosted inference ran without them.

## What 24/7 actually means

Supabase persists the queue and remains active continuously within its plan. GitHub Actions checks it on a schedule, *not* as a permanent 24/7 running process. GitHub can delay, throttle or disable schedules; it cannot run a Qwen3-VL GPU weight model for free on standard CPU-hosted Actions. A dedicated GPU/VM worker is needed for strict always-on real-time video understanding and guaranteed processing times. A no-cost unlimited 24/7 SLA cannot be honestly promised.

## Acceptance matrix (before calling production-complete)

- 20 diverse **actual**, publicly retrievable Reels; not just synthetic fixtures.
- At least five 4–20-page mixed text/images/posts, all pages accounted for and cited separately.
- Dense, short-lived links, multilingual text, speaker speech and timing checked against media.
- Every accepted URL supported by OCR/ASR/caption exact source evidence; VLM inference separated.
- Lossless duplicate DM handling, concurrent delivery, lease recovery, backoff, dead-letter requeue.
- No secret, raw provider stderr, or transient media in the public repository.
- Real operational uptime/backlog, processing success ratio and 7-day end-to-end run metrics.
- If Instagram blocks content, log the acquisition category and preserve pending evidence status; never claim zero remaining work by discarding blocked items.

## Sources (architectural rationale)

- Qwen3-VL official upstream: https://github.com/QwenLM/Qwen3-VL
- PaddleOCR upstream and PP-OCRv6/VL development: https://github.com/PaddlePaddle/PaddleOCR
- Whisper Groq transcription: https://console.groq.com/docs/speech-to-text
- gallery-dl supported public-asset retrieval: https://github.com/mikf/gallery-dl
- GitHub scheduled workflow limits: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
