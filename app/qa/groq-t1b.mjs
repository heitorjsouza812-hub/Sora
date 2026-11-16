import { readFileSync } from 'node:fs';
import { chromium } from '@playwright/test';
import { entrarNoContexto } from './entrar.mjs';
const S='qa/shots/groq-final';
const {email}=JSON.parse(readFileSync(`${S}/conta.json`,'utf8'));
const b=await chromium.launch({channel:'chrome'});
const ctx=await b.newContext({viewport:{width:1440,height:900}});
const l=await entrarNoContexto(ctx,{email}); const H={Authorization:`Bearer ${l.token_acesso}`};
const bots=await (await ctx.request.get('http://localhost:5173/v1/agentes',{headers:H})).json();
const bot=bots.find(x=>x.nome==='Analista_Preco_RidingTimes');
const page=await ctx.newPage(); await page.goto(`http://localhost:5173/bots/${bot.id}`);
await page.getByRole('textbox').waitFor(); await page.waitForTimeout(1500);
const t0=Date.now();
await page.getByRole('textbox').click(); await page.keyboard.insertText(process.env.MSG||'tente de novo: entre no site https://br.ridingtimes.com/ e diga qual é o produto mais barato, com o preço.');
await page.keyboard.press('Enter');
for(let i=0;i<60;i++){
  await page.waitForTimeout(6000);
  await page.screenshot({path:`${S}/t2-prog-${String(i).padStart(2,'0')}.png`});
  const txt=await page.locator('main').innerText().catch(()=>'');
  console.log(i,Math.round((Date.now()-t0)/1000)+'s',txt.slice(-350).replace(/\n+/g,' | '));
  const parar=await page.getByRole('button',{name:/^Parar/}).count();
  if(i>3&&!parar) break;
}
await page.screenshot({path:`${S}/t1-final-1440.png`});
await ctx.close();await b.close();
