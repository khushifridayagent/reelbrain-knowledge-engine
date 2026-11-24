# External GitHub scheduling resilience: Cloudflare Cron

This is separate from the existing Supabase metadata coordinator and
GitHub-hosted Reelbrain media worker. It only addresses the **60-day inactivity
auto-disable** risk for scheduled workflows in a PUBLIC GitHub repository.
It does **not** solve Instagram media access, paid API availability, AI model
hosting or database quota/pausing.

## Deployed infrastructure

- Cloudflare account already connected to the user, **dedicated Worker**
  `reelbrain-resilience-clock`, created 2026-11-24 09:21 UTC.
- Cloudflare **Free Cron Trigger:** `*/30 * * * *`, verified present.
- No other Workers have been changed. In particular, the existing
  `vicecut-clock` is unrelated and was left intact.
- The deployed Worker does **NOT** contain a GitHub authentication secret.
  **Current operational status: INERT**, reporting
  `disabled_missing_token`. It cannot yet trigger GitHub Actions.
- Source tracked in `deploy/reelbrain-cloudflare-clock.mjs`, unit-tested
  in `deploy/reelbrain-cloudflare-clock.test.mjs`.
- The Worker deliberately exposes no public dispatch endpoint (`fetch`
  returns 404). It logs only bounded status categories, never credentials.

## One-time activation for reliable 30-minute fallback

The user MUST add a **fine-grained GitHub personal access token** privately
to Cloudflare Workers & Pages -> `reelbrain-resilience-clock` ->
Settings -> Variables and Secrets -> **Add Secret**:

- Name: `GITHUB_TOKEN`
- Value: a fresh fine-grained PAT scoped exclusively to
  `khushifridayagent/reelbrain-knowledge-engine`, with repository
  permission **Actions: Read and write**. Set a token lifetime that
  actually covers the desired 6 months under the GitHub account policy,
  preferably longer; rotate it before expiry.
- Never use a public variable, paste the PAT into chat, or commit it to Git.

After the token exists, this independent Cloudflare clock will, every
30 minutes, perform:

```
GET /repos/khushifridayagent/reelbrain-knowledge-engine/actions/workflows/reelbrain-media-batch.yml
if disabled: PUT .../enable
POST .../dispatches with {"ref":"main"}
```

This complements, **does not replace**, the GitHub workflow's own best-effort
5-minute `schedule`. The GitHub worker still handles all DB connection
checks, lease claims, transient original-media processing, and final evidence
writes. Concurrency is serialized by the GitHub workflow and Postgres
transactional queue leases. Every 30-minute backup dispatch may run an idle
job, which performs only cheap queue preflight.

## Verification after activation

1. Inspect Cloudflare -> Worker -> Logs for
   `reelbrain_external_clock dispatched`. No HTTP status alone proves
   video extraction.
2. Confirm a `workflow_dispatch` run appears in the GitHub Actions tab
   after the next half-hour mark.
3. Compare six Reel job statuses and timestamped evidence in dedicated
   Supabase. Never mark metadata-only records as fully processed.
4. Monitor Github PAT expiration and Cloudflare Free-plan quotas. Recheck
   after 60 days of zero repository activity, if practical.
5. If no token is supplied, nothing is dispatched by Cloudflare and the
   existing GitHub `schedule` remains the only worker trigger.

Sources:
- https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows
- https://docs.github.com/en/rest/actions/workflows#enable-a-workflow
- https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/workers/platform/limits/

**Not a six-month SLA:** Cloudflare free-tier quotas, GitHub Actions
execution limits, token expiry/rotation, upstream provider outages, or
Supabase inactivity pause may still interrupt the entire extraction
pipeline. This is a low-maintenance external timing redundancy, not a GPU.
