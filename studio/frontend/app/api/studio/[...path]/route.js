import {authorized,sameOrigin} from '../../../../lib/auth.mjs';
export const runtime='nodejs';
export const dynamic='force-dynamic';
export const maxDuration=300;
const allowed=new Set(['search','detail','submit','counts']);
const reply=(x,status=200)=>Response.json(x,{status,headers:{'Cache-Control':'no-store'}});
export async function POST(req,{params}){
 if(!authorized(req.headers.get('authorization'),process.env.STUDIO_OWNER_PASSWORD))return reply({detail:'Unauthorized'},401);
 if(!sameOrigin(req.headers.get('origin'),req.headers.get('host'),process.env.STUDIO_SITE_ORIGIN))return reply({detail:'Cross-origin requests denied'},403);
 const {path}=await params;if(path.length!==1||!allowed.has(path[0]))return reply({detail:'Not found'},404);
 if(!req.headers.get('content-type')?.startsWith('application/json'))return reply({detail:'JSON required'},415);
 const target=process.env.STUDIO_BACKEND_URL,token=process.env.STUDIO_BACKEND_TOKEN;
 if(!target||!token||token.length<32)return reply({detail:'Backend not configured'},503);
 try{
  const text=await req.text();if(text.length>24000)return reply({detail:'Request too large'},413);
  const base=new URL(target);if(base.protocol!=='https:'&&base.hostname!=='localhost'&&base.hostname!=='127.0.0.1'&&base.hostname!=='backend')return reply({detail:'Backend HTTPS required'},503);
  if(base.username||base.password)return reply({detail:'Invalid backend configuration'},503);
  const r=await fetch(new URL('/'+path[0],base),{method:'POST',body:text,headers:{'content-type':'application/json',authorization:'Bearer '+token},cache:'no-store',redirect:'error',signal:AbortSignal.timeout(270000)});
  const data=await r.json();return reply(data,r.status);
 }catch{return reply({detail:'Studio backend unavailable. Retry after index preparation.'},503)}
}
