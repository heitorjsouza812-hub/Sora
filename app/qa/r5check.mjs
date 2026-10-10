import { chromium } from '@playwright/test';
const b = await chromium.launch();
const errs=[];
for (const [w,h] of [[1440,900],[390,844]]) {
  const ctx = await b.newContext({ viewport: { width: w, height: h } }); const p = await ctx.newPage();
  p.on('pageerror', e=>errs.push(w+' '+e.message)); p.on('console', m=>{ if(m.type()==='error') errs.push(w+' '+m.text()) });
  for (const r of ['/', '/projetos', '/agentes', '/plugins']) {
    await p.goto('http://localhost:5173'+r); await p.waitForTimeout(2500);
    await p.screenshot({ path: `qa/shots/r5${r.replace(/\//g,'-')||'-root'}-${w}.png` });
  }
  await ctx.close();
}
console.log(JSON.stringify(errs)); await b.close();
