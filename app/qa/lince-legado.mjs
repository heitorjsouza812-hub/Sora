// Lince — migração do localStorage legado: chaves antigas em sora.modelos.v1 devem ser apagadas ao abrir o app.
import { chromium } from '@playwright/test';
import { entrarNoContexto, BASE } from './entrar.mjs';

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext();
await entrarNoContexto(ctx);
const page = await ctx.newPage();
await page.addInitScript(() => {
  if (!localStorage.getItem('lince.semeado')) {
    localStorage.setItem('lince.semeado', '1');
    localStorage.setItem('sora.modelos.v1', JSON.stringify({
      versao: 1,
      provedores: { openai: { chave: 'sk-LEGADO-SEGREDO-123456', status: 'conectado' }, groq: { chave: 'gsk_LEGADO_654321', status: 'conectado' } },
      padraoSora: { provedor: 'openai', modelo: 'gpt-x' },
    }));
  }
});
await page.goto(`${BASE}/configuracoes`, { waitUntil: 'domcontentloaded' });
await page.waitForLoadState('networkidle');
await page.waitForTimeout(800);
const bruto = await page.evaluate(() => JSON.stringify({ ...localStorage }));
const vazou = /LEGADO/.test(bruto);
console.log(vazou ? 'FAIL chave legada continua no localStorage' : 'PASS chave legada removida do localStorage');
console.log('sora.modelos.v1 =', await page.evaluate(() => localStorage.getItem('sora.modelos.v1')));
await browser.close();
process.exit(vazou ? 1 : 0);
