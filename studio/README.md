# ReelBrain Knowledge Studio

An independent, private frontend and Agentic RAG application for an existing ReelBrain knowledge store. **No extraction code, production workflow, database tables, source rows, completed states or existing credentials were changed to build this application.**

## What is implemented

- Next.js responsive owner-only search workspace, results with source references, filters, counts, link submission, and contextual AI drawer. “A bit more detailed” selects the source(s) and prefills the detail question; public web verification is an explicit opt-in with a public query.
- FastAPI with a server-only bearer token, four fixed data endpoints and no interactive API docs. Next.js is a same-origin authenticated BFF; the browser receives neither database credentials nor provider secrets.
- Query planning via Groq (primary) / Gemini (fallback) with deterministic lexical fallback. Models do not have arbitrary SQL or write tools.
- SQLite FTS5/BM25, local multilingual E5-small embeddings, reciprocal rank fusion, and local BGE-reranker-base on the top 20 distinct source candidates. Normal result limit 8. Date, creator, tool and processing-state filters. The local persistent index is isolated and updated on demand; no extraction job is changed. Stored source text retains provenance and original locators.
- Broad keyword enumeration is paginated; per-page map-reduce summaries are optional. Exhaustive semantic recall is not certified. Exact counts come from a restricted parameterized RPC, never arbitrary text-to-SQL. Topic counts require an explicit tool filter or use keyword-match enumeration.
- Public-only research: GitHub repository search/metadata/README, TinySearch discovery and TinyFetch webpage content retrieval (public URL validation, no private query parameters, evidence from successful fetch only). Source excerpts and LLM interpretations are separate. No public code is executed. A URL found in an OCR record is not thereby verified.
- New URL submission canonicalizes direct Instagram `/reel/`, `/p/`, `/tv/` links, strips tracking and appends only if absent. No fake DM receipts, changes to existing rows, retries, or new ingestion scheduler. Existing worker continues to process its original queue.

## Structure

```
frontend/             Next.js owner UI and same-origin proxy
backend/studio/       FastAPI, index, retrieval, research and DB adapters
backend/tests/        Offline unit/integration tests with synthetic fixtures
sql/001_studio_access.sql   Optional additive isolated access facade
.github/workflows/    Independent CI (no production secrets or DB writes)
docker-compose.yml    Separate two-service local/private deployment
```

## Database connection contract — deployment step, not yet applied

The live source schema was inspected read-only: `public.reelbrain_dm_jobs`, `public.reelbrain_reel_knowledge`, `reelbrain_research.reel_observations`, `reelbrain_research.reel_resources`, `reelbrain_research.reel_sources`. The new SQL facade creates only a new `reelbrain_studio` schema and dedicated `reelbrain_studio_app` login with four narrow SECURITY DEFINER functions, explicit grants and a fixed search path. It does not change table definitions or RLS policies. Existing source tables have RLS and no PUBLIC table grants at audit time. The facade has not been applied, and role grants and runtime RLS behavior need a deployment-time audit. Do not use the existing worker's administrative DB credential.

1. Review `sql/001_studio_access.sql` and execute against the existing ReelBrain project as an authorized admin only when deploying the Studio. Confirm the new role did not previously exist with unintended grants. Check all inherited PUBLIC functions/privileges, and verify that anonymous/authenticated roles cannot invoke the new RPCs. Test with a dedicated login and a rollback-only fixture before any live submission.
2. Set a strong password for the dedicated role via an authorized secure PostgreSQL console (`\password reelbrain_studio_app` in psql). Keep it out of source, chat and shell history. Get the direct or pooler connection details from Supabase project settings; set `STUDIO_DB_URL` using only the dedicated role. For the pooler the role username includes the project suffix. Obtain the official project CA certificate; configure `STUDIO_DB_CA_CERT`. Runtime enforces TLS `verify-full` and expected project/role.
3. Copy the example env files to `backend/.env` and `frontend/.env`. Set two different strong secrets: owner password (24+ chars), and BFF/backend shared token (32+ chars). Configure the same backend token on both services. No values go into `NEXT_PUBLIC_` variables.
4. Set the persistent index path and model cache volume. Prewarm once using `python -m studio.indexer` in the backend environment before first use. The private index stores source evidence locally; disk must be private, encrypted at rest when hosted, with backups/access controls appropriate to personal data. Updates occur on demand; no scheduled task. The initial build can be slow; local E5 and BGE inference need actual CPU/memory sizing. An empty/free tiny server cannot be assumed sufficient.
5. Run `docker compose up -d --build`. The compose example binds the frontend only to local loopback, keeps the backend private and does not open a public port for it. Use a secure HTTPS reverse proxy or private network for remote access. Configure `STUDIO_SITE_ORIGIN` to the exact external HTTPS origin (local test: `http://localhost:3000`). Owner login: username `owner`, password set in server env. Never expose unencrypted Basic auth over the internet. Add hosting rate limits and access protection before making remote access available.
6. Run the Studio CI, validate auth, live retrieval, counts, citation grounding and one owner-approved real URL submit. Do not modify the media worker. Confirm the existing worker later handles the URL normally. Do not test by inserting fabricated production URLs.

## Provider choices / budget

| Credential | Needed? | Purpose |
| --- | --- | --- |
| Dedicated Studio DB login | Required for deployment | Read facade; append-only submit |
| Owner password + backend token | Required | Private access |
| Groq API key | Optional for evidence-only search; recommended for AI answers | Query rewrite and grounded synthesis |
| Gemini API key | Optional fallback | Synthesis, not free Google grounding |
| GitHub public-read token | Optional | Higher public REST limits; no private repo access needed |
| TinyFish API key | Optional for GitHub-only, needed for broad web search in this build | Public Search + Fetch; zero-credit endpoints only |
| Embedding/reranking API key | Not required | Local open models |

No provider credentials from the existing repository are copied. Prefer a separate free-tier project/account quota where allowed; a new key under the same account may share rate limits, and provider plan limits must be checked. `STUDIO_EXTERNAL_LLM_APPROVED=0` and `STUDIO_WEB_SEARCH_APPROVED=0` by default. With external LLM enabled, selected private queries/evidence are sent to the chosen provider; verify data-use settings and only enable if acceptable. With public research enabled, only the explicit public query and public repo links are used for search; private saved corpus is not sent to search providers. No paid provider is auto-enabled. TinyFish Search and Fetch are zero-credit; no paid endpoint or subscription is activated. Limits are provider-enforced; local conservative budgets are per process. Gemini 3.x free-tier Google Search grounding is unavailable in the current pricing docs.

Official references:
- https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- https://console.groq.com/docs/rate-limits
- https://ai.google.dev/gemini-api/docs/pricing
- https://api-dashboard.search.brave.com/documentation/pricing
- https://supabase.com/docs/guides/database/connecting-to-postgres

## Validation status (2026-11-25)

- Local backend: 13 passing tests covering deterministic fixture hybrid retrieval, exact URL validation, context isolation, API authentication, counts/submit contract, citation validation, GitHub response parsing, private repo exclusion and SSRF guard. Python syntax compiled.
- Frontend: 2 passing Node tests covering owner authentication and same-origin request validation. Actual Next.js build not run: environment could not resolve npm registry (`EAI_AGAIN`). CI is included to perform full build when remote repo is available.
- Database: read-only schema and query projection inspected against live DB; 11 source jobs, 8 hosted transcript rows, 11,870 evidence rows across 8 sources at audit time. No production writes, DDL, secrets, or user source data in the source bundle. SQL facade prepared, not installed; end-to-end authentication, migration and real submission not yet verified.
- Real model weights, BGE/E5 performance, external LLM/web calls and production frontend build have not been verified in this environment. Tests use synthetic embeddings and mocked provider calls, not a quality benchmark.
- New GitHub repository creation was unavailable via connected GitHub actions; browser creation failed with insufficient credits. The deliverable is an independent local Git repository (Git bundle) plus source ZIP. Neither is a public deployment. Create a private remote, then import/push this repository; never fork or overwrite the extraction repo.

## Test commands

```
cd backend
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
cd ../frontend
npm install
npm test
npm run build
```

The CI intentionally uses fixture-based tests and no private production credentials. Pin/lock exact dependency versions after the first successful online build and audit model supply-chain versions before deploying. For a small personal library, this design keeps operational overhead low; a large corpus eventually needs an indexed ANN search backend rather than a full local vector scan. Do not migrate the live worker merely to optimize Studio retrieval.
