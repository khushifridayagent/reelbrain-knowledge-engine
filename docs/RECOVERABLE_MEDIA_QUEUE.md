# Durable six-Reel recovery and 10-minute worker operating policy

Reel IDs **5, 6, 7, 8, 9, 10** are the original six user-submitted Reel jobs in the **dedicated** Supabase project `xlkdzrhzizuftbnitodr`. Each source has an existing `public.reelbrain_reel_knowledge` row. Captions/creator metadata are sparse on some rows, and **none of the six were proven media-processed at the time of this implementation**. Do not confuse researched metadata with original video decoding.

## Improvements

- Live SQL migration `sql/0025_media_access_backoff.sql`: a leased job that fails due to Instagram 429, 403, login requirement, or unavailable media is **deferred** with a bounded wait (2 h generic / 6 h denied / 12 h rate limited) and returned to `queued`, without decrementing its finite software-bug retry budget permanently. `access_deferred_count` tracks real external access failures; normal worker exceptions keep the existing finite retry/dead-letter handling.
- Existing dead-letter job **5** can be safely returned to `queued` after inspecting its previous access failure; do not erase its `last_error` or fake processing success.
- A 10-minute GitHub Actions **queue peek** now connects using a lightweight `psycopg` preflight first. If no eligible media is available yet, it does **not** spend every scheduled run reinstalling Tesseract, FFmpeg, Whisper, yt-dlp, and gallery-dl. When eligible jobs exist, actual extraction runs normally and reports red on failed access.
- The separate owner-access monitoring automation checks the six original jobs and new approved-sender submissions hourly. It can alert on a stalled queue, media failure, or completion; it is not a substitute for the repository's scheduled worker or new credentials.

## Interpret statuses

| DB status | Meaning |
|---|---|
| queued, available_at in future | Waiting for external-media access backoff; still retained |
| queued, available_at <= now | Eligible for next scheduled media attempt |
| leased | A worker has claimed the Reel temporarily |
| partial | Actual media has a persisted receipt but incomplete modalities |
| processed | Real persisted media evidence was saved and the claim acknowledged |
| dead_letter | Repeated software/queue failures exhausted attempts or a previous legacy access failure; never silently discard |

The deferred access count and the last category of error are retained; no secret or original media is stored in GitHub code.

## Manual verification queries

```sql
SELECT id,status,attempts,access_deferred_count,available_at,
       LEFT(COALESCE(last_error,''),120) last_error
FROM public.reelbrain_dm_jobs
WHERE id IN (5,6,7,8,9,10)
ORDER BY id;

SELECT k.processing_stage,COUNT(*) n,
       SUM(k.video_analyzed::int) video,
       SUM(k.audio_transcribed::int) audio,
       SUM(k.ocr_analyzed::int) ocr
FROM public.reelbrain_reel_knowledge k
JOIN public.reelbrain_dm_jobs j ON j.source_url=k.source_url
WHERE j.id IN (5,6,7,8,9,10)
GROUP BY k.processing_stage;
```

**Note:** External Instagram rate limits and datacenter blocks cannot be fixed purely by increasing job retries. The optional Instagram-only session secret `REELBRAIN_INSTAGRAM_COOKIES_B64` or an authorized media delivery source remains the real acquisition requirement for blocked URLs. No separate password, payment, or GPU has been configured by this change. A job only becomes `processed` after media evidence actually saves. Never hide 403/429 by marking source complete.
