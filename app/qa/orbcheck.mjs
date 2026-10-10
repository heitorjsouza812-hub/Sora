import { chromium } from '@playwright/test';
const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
await p.goto('http://localhost:5173/'); await p.waitForTimeout(7000);
await p.screenshot({ path: 'qa/shots/home-7s.png', clip: { x: 700, y: 160, width: 340, height: 280 } });
await p.goto('http://localhost:5173/lab/orb?solo=240&state=idle&t=4'); await p.waitForTimeout(2500);
await p.screenshot({ path: 'qa/shots/solo-idle.png' });
await b.close();
