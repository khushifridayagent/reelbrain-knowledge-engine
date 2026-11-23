# Meta one-to-one Instagram DM webhook (Reelbrain)

This Deno Edge Function is a **signed webhook receiver**, not an Instagram scraper, video analysis worker or an auto-responder. Deploy with JWT verification **disabled** for the webhook itself because Meta calls cannot send Supabase JWTs. Incoming POSTs require Meta's `X-Hub-Signature-256` HMAC, account recipient validation and a sender allowlist. GET verifies the challenge token. It queues canonical links only and acknowledges quickly. Invalid or missing configuration fails closed (503).

Set secrets only on the new dedicated Reelbrain project via Supabase secrets UI (never in Git, Meta comments, or the public page): `META_APP_SECRET`, `META_VERIFY_TOKEN` (choose random), `META_IG_PROFESSIONAL_ID` (correct recipient), `META_ALLOWED_SENDERS` (three exact sender IDs), plus the platform-provided `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`. Instagram Professional account and Meta app with `instagram_business_manage_messages` are required; some users and production use require review/advanced access. Subscribe to the Instagram `messages` webhook field. Shared media webhook supplies URLs, not the video bytes. Group messaging is unsupported by the official API.

The function runs on Supabase Edge Functions but actual media OCR/ASR/VLM requires a separately deployed worker. Never expose Supabase service keys to clients.
