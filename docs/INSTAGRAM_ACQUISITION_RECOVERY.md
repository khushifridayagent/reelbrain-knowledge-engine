# Instagram media acquisition: operational diagnosis and recovery

## Why current anonymous downloads fail

Real Reelbrain worker runs established that the dedicated Supabase URI is valid, the queue claims jobs, and video dependencies install correctly. What fails is **receiving original Instagram media bytes** from the GitHub datacenter runner. Recent provider failures included HTTP 403 (forbidden), HTTP 429 (rate limited), and extractor-unavailable responses through both `yt-dlp` and `gallery-dl`. Those reflect Instagram access/rate-limiting or extractor limitations; they are **not** a missing local Python folder or Qwen model failure.

An Instagram Reel can be public *in the Instagram app* yet Instagram may refuse an anonymous non-browser request from a datacenter IP. A second downloader alone does not overcome account/session requirements or rate limits.

## Optional user-owned authenticated session

The new worker can use a user-managed **Instagram-only Netscape cookies.txt** for content that the account is authorized to access. The code accepts only cookies for the Instagram domain and writes them to a file that is deleted when acquisition finishes. Cookies are never stored in the public repository or in Supabase knowledge rows. This is optional: without a configured secret the existing anonymous path continues.

1. From your own signed-in Instagram account, generate a Netscape-format cookies.txt *only for Instagram*. Browser extensions are third-party; assess their trust before installing. **Do not send cookies, passwords or the session to anyone in chat.** Treat exported cookies as account credentials.
2. Base64-encode the local cookies.txt and privately set the **repository Actions secret** `REELBRAIN_INSTAGRAM_COOKIES_B64` in **Settings → Secrets and variables → Actions**. Never add this as a public variable, file committed to Git, or paste the base64 value into chat.
3. The existing scheduled GitHub media workflow automatically passes the secret to the worker. On the next scheduled job, it temporarily decodes, validates, and uses the session through both yt-dlp and gallery-dl; it then deletes the plaintext file.
4. Look at actual media ingestion results in `reelbrain_dm_jobs` and the provenance flags in `reelbrain_reel_knowledge`. **Do not treat a passing scheduler check as evidence that video/audio was decoded.** Instagram may still block this approach, or the session may expire; cookies are not a guarantee.
5. A job already in `dead_letter` is intentionally not automatically claimed. After resolving access and proving a successful test with a valid asset, requeue its exact ID under controlled operator review to prevent endless attempts/account lockout.

This integration never asks for Instagram account passwords and it does not grant access beyond the user-authenticated session's permissions. Respect access restrictions; do not rely on it to obtain content the account cannot legitimately access.

## GPU reality

GitHub's normal `ubuntu-24.04` hosted worker is **CPU-only**. The Qwen3-VL-8B model code is wired as an *OpenAI-compatible inference client* and requires an actual service exposing a compatible `/v1/chat/completions` API, typically GPU-backed. GitHub offers paid GPU larger runners for eligible Team/Enterprise organizational accounts, but a standard personal repository does not receive a persistent free GPU by pushing a model to GitHub. GitHub Actions is a batch scheduler, not a guaranteed always-on server. A self-hosted GPU runner or a managed inference provider is an alternative, with its own operational constraints and costs. No paid GPU resource has been provisioned by this change.

## Recovery acceptance criteria

- At least one genuine Instagram Reel returns authenticated media bytes and is verified with ffprobe before reporting any decoding.
- Each media subtype (video, carousel image, mixed slides) yields the correct distinct source timestamp/page evidence.
- Local Whisper provides timestamped speech evidence, not just a caption.
- Qwen3-VL is reported as running only when a real endpoint responds and observed frames are analyzed.
- Previously exhausted jobs are not marked processed based on metadata alone.
