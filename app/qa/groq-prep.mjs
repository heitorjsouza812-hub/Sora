import { readFileSync } from 'node:fs';
import { chromium } from '@playwright/test';
import { entrarNoContexto } from './entrar.mjs';
const {email}=JSON.parse(readFileSync('qa/shots/groq-final/conta.json','utf8'));
const off=(process.env.OFF||'').split(',').filter(Boolean), on=(process.env.ON||'').split(',').filter(Boolean);
const b=await chromium.launch({channel:'chrome'}); const ctx=await b.newContext();
const l=await entrarNoContexto(ctx,{email}); const H={Authorization:`Bearer ${l.token_acesso}`};
const U='http://localhost:5173/v1';
const ms=await (await ctx.request.get(`${U}/modelos`,{headers:H})).json();
for(const m of ms){const nome=m.modelo.replace('groq/','');
  const quer = on.includes(nome)?true: off.includes(nome)?false:null; if(quer===null||quer===m.ativo)continue;
  const r=await ctx.request.patch(`${U}/modelos/${m.id}`,{headers:H,data:{ativo:quer}}); console.log(nome,quer,r.status());}
if(process.env.APAGAR){const bs=await (await ctx.request.get(`${U}/agentes`,{headers:H})).json();
 for(const a of bs) if(a.tipo==='individual'&&a.nome!=='Sora'){console.log('del',a.nome,(await ctx.request.delete(`${U}/agentes/${a.id}`,{headers:H})).status());}}
await ctx.close();await b.close();
