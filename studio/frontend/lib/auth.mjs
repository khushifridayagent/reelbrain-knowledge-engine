import {timingSafeEqual} from 'node:crypto';
export function authorized(header,secret){
 if(typeof secret!=='string'||secret.length<24||typeof header!=='string'||!header.startsWith('Basic '))return false;
 try{const raw=Buffer.from(header.slice(6),'base64').toString('utf8');const expected=Buffer.from('owner:'+secret);const actual=Buffer.from(raw);return expected.length===actual.length&&timingSafeEqual(expected,actual)}catch{return false}
}
export function sameOrigin(origin,host,configured){
 if(!origin)return false;
 try{const o=new URL(origin);if(configured)return o.origin===new URL(configured).origin;return o.host===host&&['https:','http:'].includes(o.protocol)}catch{return false}
}
