/**
 * Reelbrain 6-month-resilience clock. Cloudflare Workers Free Cron (opt-in).
 *
 * GitHub's public repository workflows may be disabled after 60 days with no
 * repository activity. This tiny *independent* clock uses a private,
 * fine-grained GitHub Actions-only PAT to re-enable the workflow if needed and
 * workflow_dispatch it. No Reel URLs, database rows or video bytes leave
 * Supabase. The actual compute runs on GitHub Actions, not Cloudflare.
 *
 * Worker is completely inert until a valid Cloudflare secret GITHUB_TOKEN is
 * configured privately; no hard-coded token can be stored in this public repo.
 */

const REPO='khushifridayagent/reelbrain-knowledge-engine';
const WORKFLOW='reelbrain-media-batch.yml';
const BASE=`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}`;

function statusForHTTP(code){
  if(code===401||code===403)return 'github_access_denied';
  if(code===404)return 'workflow_unavailable';
  if(code===429)return 'github_rate_limited';
  return 'github_http_failure';
}

export async function dispatchOnce(env, requestFetch=fetch){
  const token=env?.GITHUB_TOKEN;
  if(typeof token!=='string'||token.length<1)return 'disabled_missing_token';
  const headers={
    'Accept':'application/vnd.github+json',
    'Authorization':`Bearer ${token}`,
    'X-GitHub-Api-Version':'2022-11-28',
    'User-Agent':'Reelbrain-Cloudflare-External-Clock/1',
  };
  const request=async(method,url,body)=>{
    const opts={method,headers:{...headers},signal:AbortSignal.timeout(7500)};
    if(body!==undefined){opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(body)}
    return requestFetch(url,opts);
  };
  try{
    const get=await request('GET',BASE);
    if(!get.ok)return statusForHTTP(get.status);
    const info=await get.json();
    if(!info||typeof info.state!=='string')return 'invalid_github_response';
    // Respect an explicit operator pause. Only the platform inactivity state
    // is eligible for autonomous reactivation.
    if(info.state!=='active'&&info.state!=='disabled_inactivity')return 'workflow_disabled';
    if(info.state==='disabled_inactivity'){
      // A once-active repository can become disabled by GitHub's 60-day
      // inactivity policy. Scoped Actions write permission is required.
      const enabled=await request('PUT',BASE+'/enable');
      if(!enabled.ok)return statusForHTTP(enabled.status);
    }
    // A GitHub concurrency group allows one running and one pending run.
    // Do not replace an existing successor; allow exactly one queued successor
    // to preserve throughput across long-running media batches. Fail closed if
    // the API cannot establish the queue state. The native hourly cron remains
    // an independent liveness fallback.
    const runs=await request('GET',BASE+'/runs?per_page=50');
    if(!runs.ok)return statusForHTTP(runs.status);
    const snapshot=await runs.json();
    if(!Array.isArray(snapshot?.workflow_runs))return 'invalid_github_response';
    const pendingStates=new Set(['queued','pending','waiting','requested']);
    for(const run of snapshot.workflow_runs){
      if(pendingStates.has(run?.status))return 'already_queued';
      if(run?.status!=='in_progress'&&run?.status!=='completed')return 'invalid_github_response';
    }
    // The workflow itself verifies the dedicated DB secret and checks for
    // eligible queue jobs, skipping heavy installations when the queue is idle.
    const trigger=await request('POST',BASE+'/dispatches',{ref:'main'});
    if(!trigger.ok)return statusForHTTP(trigger.status);
    return 'dispatched';
  }catch(_error){
    // Never log request headers or secrets. No automatic retry storms.
    return 'github_unreachable';
  }
}

export default {
  async scheduled(_controller, env, _ctx){
    const status=await dispatchOnce(env);
    // A short fixed result category enables Cloudflare cron-health monitoring.
    console.log('reelbrain_external_clock',status);
  },
  async fetch(_request,_env){
    // No public endpoint may trigger the queue or reveal secrets.
    return new Response('Not found',{status:404,headers:{'Cache-Control':'no-store'}});
  }
};
