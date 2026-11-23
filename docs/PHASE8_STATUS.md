# Phase 8: 1:1 Instagram DM intake, queue, search interface, and external research

## Verified state (2026-11-23)

- Dedicated allowed repo **only**: `khushifridayagent/reelbrain-knowledge-engine`. The user-created repository is **PUBLIC** (not private). Never commit private chat logs, tokens, media, database exports or uploaded archives. Other repos untouched.
- Dedicated Supabase project **only**: `Reelbrain Knowledge` / `xlkdzrhzizuftbnitodr` (Mumbai). Historical catalog (2,406 repositories) preserved.
- Durable queue SQL: idempotency on canonical Reel URL, atomic `SKIP LOCKED` leases, exponential retry, dead-letter status and lease-expiry recovery. Scripted integration tests are needed on staging for race/fault cases.
- Signed webhook: GET Meta challenge, POST HMAC verification, expected receiver and sender allowlist, hashes sender and message IDs; stores only canonical Reel/post URL; never processes private group chats or auto-replies. Supabase Edge Function live **but not yet configured for real Instagram account**.
- New private-search website source: owner-token protected, catalog + Reel citation search, Reel URL submission; separate `A bit more` GitHub README/metadata review without database writes. Not yet deployed to public hostname.
- Independent model APIs: local multimodal OCR + optional Groq ASR + Gemini video, by explicit owner permissions/keys. No real 20-Reel golden set has passed. No evidence of 3-minute video processing in 3 seconds with human-level understanding. 24/7 worker hosting is **not configured**.
- `requirements-site.txt` plus `requirements-web.txt`, `requirements.txt` for app modules.

## Meta setup needed

1. Create a Meta developers app with Instagram product and link a **Professional** Instagram account. Verify account roles and the proper `instagram_business_manage_messages` permission, webhook subscription and app review/advanced access depending on recipient roles. Ensure the three sending accounts have permission to message the Professional account.
2. Add Supabase Edge Function secrets for the isolated project: `META_APP_SECRET`, `META_VERIFY_TOKEN`, `META_IG_PROFESSIONAL_ID`, `META_ALLOWED_SENDERS` and Supabase-provided endpoint/key values. **Never paste live credentials in GitHub.** Allowlist actual Instagram-scoped sender IDs (not usernames).
3. Set Meta messages webhook callback to the deployed function's URL, verify challenge and run one controlled real DM test. No live DM receipt is claimed yet. Existing/new group chats cannot be read by the official Instagram Messaging API.

## Operational costs and boundaries

- No hosting provider offers genuinely unlimited, guaranteed always-on GPU video processing for free. Supabase Free Edge Functions impose CPU/memory/runtime/usage limits. A persistent or periodically scheduled paid/free-quota worker host is required for OCR/ASR/VLM. No unauthorized 3rd-party Reel scraping or model upload is started by this release.
- Optical/speech/vision extraction completeness is unproven until manually labeled real videos establish precision/recall, error modes, tool/procedure coverage, and reliability. GitHub README explanations are **publisher claims**, not laboratory-tested software capabilities.
- Meta 1:1 API supports shared Reel URL attachment notifications; Meta does not provide arbitrary playback media bytes for every third-party Reel.
- All stage transitions require real receipts. Uploading this repository is **not** deploying a functional 24/7 worker or connecting Instagram messaging.
