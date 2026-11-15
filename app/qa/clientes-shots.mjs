// Screenshots de /clientes e Configurações → Canais da empresa (1440 e 390), contra API e Vite reais.
import { chromium } from '@playwright/test';
process.env.SORA_QA_BASE ??= 'http://localhost:5173';
const { entrarNoContexto } = await import('./entrar.mjs');
const BASE = process.env.SORA_QA_BASE ?? 'http://localhost:5173';
const b = await chromium.launch();
let erros = 0;
for (const [nome, w, h] of [['desktop', 1440, 900], ['celular', 390, 844]]) {
  const ctx = await b.newContext({ viewport: { width: w, height: h } });
  await entrarNoContexto(ctx, { email: 'qa-design@sora.local' });
  const p = await ctx.newPage();
  p.on('console', m => { if (m.type() === 'error') { erros++; console.log('console:', m.text()); } });
  for (const [id, url] of [['clientes', '/clientes'], ['canais', '/configuracoes?secao=canais-empresa']]) {
    await p.goto(BASE + url, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(2000);
    await p.screenshot({ path: `qa/shots/clientes/${id}-${nome}.png`, fullPage: true });
    console.log(id, nome, (await p.locator('main, body').first().innerText()).slice(0, 160).replace(/\n/g, ' | '));
  }
  await ctx.close();
}
await b.close();
console.log('erros de console:', erros);
