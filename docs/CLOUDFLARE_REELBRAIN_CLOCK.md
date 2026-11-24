# External GitHub scheduling resilience: Cloudflare Cron

This is separate from the existing Supabase metadata coordinator and
GitHub-hosted Reelbrain media worker. It only addresses the **60-day inactivity
auto-disable** risk for scheduled workflows in a PUBLIC GitHub repository.
It does **not** solve Instagram media access, paid API availability, AI model
hosting or database quota/pausing.

## Deployed infrastructure

- Cloudflare account already connected to the user, **dedicated Worker**
  `reelbrain-resilience-clock`, created 2026-11-24 09:21 UTC.
- Cloudflare **Free Cron Trigger:** `*/5 * * * *`, verified present on 2026-11-24 11:20 UTC. Schedule changes can take up to ~15 minutes to propagate.
- No other Workers have been changed. In particular, the existing
  `vicecut-clock` is unrelated and was left intact.
- The deployed Worker has the private **`GITHUB_TOKEN`** secret (presence verified without inspecting its value). It successfully dispatched GitHub Actions `workflow_dispatch` runs #45375468067 and #45380156392. These runs prove scheduling works, but Instagram media retrieval still fails independently.
- Source tracked in `deploy/reelbrain-cloudflare-clock.mjs`, unit-tested
  in `deploy/reelbrain-cloudflare-clock.test.mjs`.
- The Worker deliberately exposes no public dispatch endpoint (`fetch`
  returns 404). It logs only bounded status categories, never credentials.

## Current active five-minute external scheduling

The user already installed a GitHub classic PAT privately in Cloudflare Workers & Pages -> `reelbrain-resilience-clock` -> Settings -> Variables and Secrets. **No new token is needed now.** When rotating later, prefer a fine-grained token restricted to this repository:

- Name: `GITHUB_TOKEN`
- Future rotation preference: a fresh fine-grained PAT scoped exclusively to
  `khushifridayagent/reelbrain-knowledge-engine`, with repository
  permission **Actions: Read and write**. Set a token lifetime that
  actually covers the desired 6 months under the GitHub account policy,
  preferably longer; rotate it before expiry.
- Never use a public variable, paste the PAT into chat, or commit it to Git.

The independently deployed Cloudflare clock now triggers every **five minutes** and performs:

```
GET /repos/khushifridayagent/reelbrain-knowledge-engine/actions/workflows/reelbrain-media-batch.yml
if disabled: PUT .../enable
POST .../dispatches with {"ref":"main"}
```

This complements, **does not replace**, the GitHub workflow's own best-effort
5-minute `schedule`. The GitHub worker still handles all DB connection
checks, lease claims, transient original-media processing, and final evidence
writes. Concurrency is serialized by the GitHub workflow and Postgres
transactional queue leases. Every five-minute backup dispatch may run an idle
job, which performs only cheap queue preflight.

## Verification after activation

1. Inspect Cloudflare -> Worker -> Logs for
   `reelbrain_external_clock dispatched`. No HTTP status alone proves
   video extraction.
2. Confirm a `workflow_dispatch` run appears in the GitHub Actions tab
   after the new five-minute Cron schedule propagates; then confirm actual dispatched run status.
3. Compare six Reel job statuses and timestamped evidence in dedicated
   Supabase. Never mark metadata-only records as fully processed.
4. Monitor Github PAT expiration and Cloudflare Free-plan quotas. Recheck
   after 60 days of zero repository activity, if practical.
5. Cloudflare `GITHUB_TOKEN` is already set and has produced real dispatched runs. Avoid replacing a working secret with the separate `GITHUB_DISPATCH_TOKEN` label appearing in the uploaded third-party report; that report describes a different dispatch mechanism (`repository_dispatch`, not this Worker’s actual `workflow_dispatch`).

Sources:
- https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows
- https://docs.github.com/en/rest/actions/workflows#enable-a-workflow
- https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/workers/platform/limits/

**What is and is not proved:** Cloudflare triggering works (GitHub `workflow_dispatch` observed), and six of six original URLs now have real hosted audio transcripts with timestamps, persisted and searchable as of 2026-11-24. All six original media jobs remain pending independent video/frames/OCR; real Instagram acquisition is still blocked. `REELBRAIN_HOSTED_TRANSCRIPT_DAILY_LIMIT=60` is ignored by the selected TranscriptFetch credit-aware worker and does not limit new URL receipts. Workers will pause at actual provider zero credits/402/429 and automatically retry if provider credits actually replenish. The 50 free credits may be one-time and are NOT a promise of monthly renewal. No automatic paying or overage is activated.

**Not a six-month SLA:** Cloudflare free-tier quotas, GitHub Actions
execution limits, token expiry/rotation, upstream provider outages, or
Supabase inactivity pause may still interrupt the entire extraction
pipeline. This is a low-maintenance external timing redundancy, not a GPU.
