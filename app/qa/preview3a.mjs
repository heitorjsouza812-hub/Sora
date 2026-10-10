import { chromium } from '@playwright/test';
const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
const errs=[]; p.on('pageerror', e=>errs.push(e.message)); p.on('console', m=>{ if(m.type()==='error') errs.push(m.text()) });
await p.goto('http://localhost:5173/lab/orb#agentes'); await p.waitForTimeout(3000);
await p.screenshot({ path: 'qa/shots/r3a-agentes.png' });
await p.goto('http://localhost:5173/lab/orb#trabalho'); await p.waitForTimeout(12000);
await p.screenshot({ path: 'qa/shots/r3a-trabalho.png' });
console.log(JSON.stringify(errs));
await b.close();
