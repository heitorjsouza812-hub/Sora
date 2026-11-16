import { readFileSync } from 'node:fs';
import { chromium } from '@playwright/test';
import { entrarNoContexto } from './entrar.mjs';
const S='qa/shots/groq-final', tag=process.env.TAG;
const {email}=JSON.parse(readFileSync(`${S}/conta.json`,'utf8'));
const b=await chromium.launch({channel:'chrome'});
const ctx=await b.newContext({viewport:{width:1440,height:900}});
await entrarNoContexto(ctx,{email});
const page=await ctx.newPage(); await page.goto('http://localhost:5173/');
await page.getByRole('textbox').waitFor(); await page.waitForTimeout(2500);
const t0=Date.now();
await page.getByRole('textbox').click(); await page.keyboard.insertText(process.env.MSG);
await page.keyboard.press('Enter');
for(let i=0;i<20;i++){ await page.waitForTimeout(6000);
  await page.screenshot({path:`${S}/${tag}-${String(i).padStart(2,'0')}.png`});
  const txt=await page.locator('main').innerText().catch(()=>'');
  console.log(i,Math.round((Date.now()-t0)/1000)+'s',txt.slice(-400).replace(/\n+/g,' | '));
  if(i>2 && !(await page.getByRole('button',{name:/^Parar/}).count())) break; }
await ctx.close();await b.close();
