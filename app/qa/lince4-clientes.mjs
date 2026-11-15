// Confere ao vivo a barra lateral (Clientes com lugar próprio), a aba de conhecimento e o console limpo.
import { chromium } from '@playwright/test';
process.env.SORA_QA_BASE ??= 'http://localhost:5173';
const { entrarNoContexto } = await import('./entrar.mjs');
const base = process.env.SORA_QA_BASE;
const browser = await chromium.launch();
let falhou = false;
try {
  for (const [w, h] of [[1440, 900], [390, 844]]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    await entrarNoContexto(ctx, {});
    const page = await ctx.newPage();
    const erros = [];
    page.on('console', m => { if (m.type() === 'error') erros.push(m.text()); });
    await page.goto(base + '/clientes');
    if (w < 700) await page.getByRole('button', { name: /menu|navegação/i }).first().click().catch(() => undefined);
    const item = page.locator('a.shell-clientes:visible').first();
    await item.waitFor({ state: 'visible', timeout: 15000 });
    const dentroDeGrupos = await item.evaluate(el => !!el.closest('section.shell-section'));
    if (dentroDeGrupos) throw new Error('Clientes ainda está dentro de uma seção');
    await page.screenshot({ path: `qa/shots/lince4-barra-${w}.png` });
    if (w < 700) await page.keyboard.press('Escape');
    await page.getByRole('button', { name: /O que a Sora aprendeu/ }).click();
    await page.getByText('Para aprovar').first().waitFor({ timeout: 15000 });
    await page.screenshot({ path: `qa/shots/lince4-conhecimento-${w}.png`, fullPage: true });
    if (erros.length) throw new Error(`console sujo (${w}): ${erros.join(' | ')}`);
    await ctx.close();
  }
  // sem marca de sessão: nenhuma chamada a /auth/renovar e console limpo
  const ctx = await browser.newContext(); const page = await ctx.newPage();
  const renovar = []; const erros = [];
  page.on('request', r => { if (r.url().includes('/auth/renovar')) renovar.push(r.url()); });
  page.on('console', m => { if (m.type() === 'error') erros.push(m.text()); });
  await page.goto(base + '/'); await page.getByRole('button', { name: 'Entrar', exact: true }).first().waitFor({ timeout: 15000 });
  if (renovar.length || erros.length) throw new Error(`sem sessão: renovar=${renovar.length} erros=${erros.join('|')}`);
  console.log('OK lince4-clientes');
} catch (e) { falhou = true; console.error(e); } finally { await browser.close(); }
process.exit(falhou ? 1 : 0);
