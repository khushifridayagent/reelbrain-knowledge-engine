# Phase 8 source comparison (23 November 2026)

Research sources are dated **at the time of review**. These are candidates, not benchmark winners.

| Layer | Candidate | Verified publisher claim / evidence | Decision and limitation |
| --- | --- | --- | --- |
| 1:1 inbound DM | Meta Instagram Messaging API | Meta changelog (Jun 11, 2024) added **ig_reel** shared attachments with a URL; Meta API Postman documentation says **group messaging is unsupported**. | Use professional account **one-to-one** messaging webhook and expect a URL, not arbitrary third-party video bytes. Real account test still missing. |
| Visible video understanding | Qwen3-VL | Maintained QwenLM/Qwen3-VL repository documents video OCR, grounding and long video context. | Evaluate on annotated 20-Reel dataset. Hosting GPU RAM/cost and Hindi speech not benchmarked. |
| Fast speech transcription | Groq Whisper Large v3 Turbo | Groq official STT documentation advertises turbo inference and segment timestamps. | Optional API adapter, rate limits, language/code-switching accuracy unmeasured. |
| Exact onscreen text | PaddleOCR / PaddleOCR-VL | Official PaddlePaddle docs list multilingual OCR and document parsing, including Hindi for VL. | Optional candidate for dynamic frame/slide OCR; no substitute for testing compressed Reels and 0.3-second links. |
| Media acquisition | Official Meta or authorized upload, replaceable provider adapters | Meta's messaging webhook contains source URL, not guaranteed playable MP4; 3rd-party providers may restrict access and pricing. | Source access, legitimate rights, provider choice and signed receipts are independent concerns. Apify is **not** the intelligence engine and is not a required winner. |
| 24/7 infrastructure | Hosted Postgres + edge intake + separate worker | Supabase Free Edge Functions have documented wall/CPU/memory limits, and free project pausing can occur after inactivity. | Cannot guarantee unlimited processing, free, 24/7 availability. Set cost caps and test backpressure. |

Sources:
- https://developers.facebook.com/documentation/business-messaging/instagram-messaging/changelog/
- https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api
- https://github.com/QwenLM/Qwen3-VL
- https://github.com/PaddlePaddle/PaddleOCR
- https://console.groq.com/docs/speech-to-text
- https://supabase.com/docs/guides/functions/limits
- https://supabase.com/docs/guides/platform/free-project-pausing

## Gold tests before claiming “3 minutes → 3 seconds”

Measure the entire chain on **20 diverse real Reels with permission and manual ground truth** (then 50/100):
1. Source acquisition success/denial (never imply accessible if unavailable).
2. Speech WER/CER in Hindi-English code-switching; missing captions and audio.
3. Keyframe OCR exact URL precision and recall, ephemeral links (<0.5 seconds), overlay movement, slides.
4. Complete fact/unit/procedure/link extraction against manual annotations, confidence with evidence timestamps and explicit unresolved.
5. Verification distinguishes “creator said”, “README said”, “independently checked” and “sandbox tested”.
6. P50, P95 and P99 wall-clock with transfer/queue/provider latency, real dollars per Reel, 100-Reel burst drain and dead-letter/retries.
7. Secure configuration, Meta app review, failures on unreachable/removed media, duplicate DM idempotency, SQL tenant privacy.

Do not mark these gates passed without recorded observations or actual provider/worker receipts.
