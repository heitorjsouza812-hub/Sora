import { chromium } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const base = process.env.SORA_URL || 'http://localhost:5173';
const out = path.resolve('qa/shots');
await fs.mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true });
const erros = [];
for (const viewport of [{ name: '1440', width: 1440, height: 980 }, { name: '390', width: 390, height: 844 }]) {
  const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height }, deviceScaleFactor: 1 });
  page.on('console', msg => { if (msg.type() === 'error') erros.push(`${viewport.name}: ${msg.text()}`); });
  page.on('pageerror', error => erros.push(`${viewport.name}: ${error.message}`));
  for (const [tela, rota] of [['configuracoes', '/configuracoes'], ['agente', '/agentes/novo']]) {
    await page.goto(`${base}${rota}`, { waitUntil: 'networkidle' });
    const largura = await page.evaluate(() => ({ pagina: document.documentElement.scrollWidth, janela: document.documentElement.clientWidth }));
    if (largura.pagina > largura.janela) erros.push(`${viewport.name}/${tela}: scroll horizontal (${largura.pagina}px > ${largura.janela}px)`);
    await page.screenshot({ path: path.join(out, `r4-${tela}-${viewport.name}.png`), fullPage: true });
    if (tela === 'configuracoes') {
      await page.locator('.cfg-provider-summary').first().click();
      await page.screenshot({ path: path.join(out, `r4-${tela}-aberta-${viewport.name}.png`), fullPage: true });
    } else {
      await page.locator(viewport.width < 768 ? '.bld-mobile-tabs button' : '.bld-tabs button').filter({ hasText: 'Configurar' }).click();
      await page.screenshot({ path: path.join(out, `r4-${tela}-configurar-${viewport.name}.png`), fullPage: true });
      if (viewport.width < 768) {
        await page.locator('.bld-mobile-tabs button').filter({ hasText: 'Prévia' }).click();
        await page.screenshot({ path: path.join(out, `r4-${tela}-previa-${viewport.name}.png`), fullPage: true });
      }
    }
  }
  await page.close();
}
await browser.close();
if (erros.length) { process.stderr.write(`${erros.join('\n')}\n`); process.exitCode = 1; }
else process.stdout.write('Preview 4 capturada sem erros de console.\n');

