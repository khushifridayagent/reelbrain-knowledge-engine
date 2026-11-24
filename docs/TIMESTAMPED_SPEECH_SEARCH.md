# Real speech evidence — timestamped retrieval

## Live verified 2026-11-24

All six initial Reel URLs now have provider **spoken audio transcripts** stored
in `public.reelbrain_reel_knowledge.verified_reel_content->'provider_audio_transcript'`.
This is not merely a creator's typed Instagram caption. Source provider is
TranscriptFetch, with timestamp segments saved alongside full original ASR text.

Original Instagram frames, slide text, OCR or independently verified scene
descriptions still **remain unproven** because GitHub datacenter media
acquisition encounters Instagram 403/429. Never represent 6/6 speech as
6/6 full multimedia understanding.

The separate 6 rows in `public.reelbrain_dm_jobs` remain `queued` for
full original media acquisition/visual analysis, even when speech is saved.

## SQL search examples (private backend; no frontend required)

```sql
-- Named resource inside ACTUAL provider-spoken audio, with timestamps:
SELECT source_url,provider,start_seconds,end_seconds,spoken_text
FROM reelbrain_research.search_reel_speech_segments('Paperclip',10)
ORDER BY start_seconds;

-- Verify broad keyword research search still includes the FULL speech:
SELECT repo_url,verification_level,source_locator,what_it_does
FROM reelbrain_research.search_reels('dashboard shows every task',12);

-- Observe whether each Reel has independent media/video/OCR:
SELECT source_url,
       verified_reel_content ? 'provider_audio_transcript' AS hosted_speech,
       video_analyzed,ocr_analyzed,processing_stage
FROM public.reelbrain_reel_knowledge
ORDER BY source_url;
```

The new `search_reel_speech_segments` function only reads provider-supplied
actual segments and returns `third_party_url_speech_segment` as evidence
type. It never labels visual content as verified and only searches terms
spoken in the transcript.

**Verified query:** Paperclip returned two timed excerpts at 0–29s
and 58.6–64.46s; a deliberately nonexistent visual keyword returned 0.

## Capacity and credits

For the selected TranscriptFetch provider, there is no user-imposed
60/day ceiling. Each GitHub execution claims at most four new ASR jobs
within 210s, then exits, and the next trigger resumes. Cloudflare backup
clock is `*/5 * * * *` (up to 15min propagation); Postgres queue
persists regardless of scheduling delay. Every new start checks the free
`GET /api/v2/me` credit balance; at 0 or 402/429 jobs are deferred,
not lost, and no automatic payment is made. Provider credits may be
non-renewing; the worker can resume only when real account credits
increase. Do not mistake 10k Cloudflare Workers AI daily Neurons for
TranscriptFetch's separately metered starter credits.
