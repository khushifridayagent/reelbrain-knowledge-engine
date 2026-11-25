import {NextResponse} from 'next/server';
import {authorized} from './lib/auth.mjs';
export function proxy(req){
 const secret=process.env.STUDIO_OWNER_PASSWORD;
 if(!secret||secret.length<24)return new NextResponse('Private Studio not configured',{status:503,headers:{'Cache-Control':'no-store'}});
 if(!authorized(req.headers.get('authorization'),secret))return new NextResponse('Private Studio',{status:401,headers:{'WWW-Authenticate':'Basic realm="ReelBrain Private Studio", charset="UTF-8"','Cache-Control':'no-store'}});
 return NextResponse.next();
}
export const config={matcher:['/((?!_next/static|_next/image|favicon.ico).*)']};
