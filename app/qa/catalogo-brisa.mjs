// QA do catálogo de componentes base (/lab/ui): página inteira, tooltip pelo teclado + Esc, toasts e Desfazer.
// Uso: node qa/catalogo-brisa.mjs   (dev server em http://localhost:5173)
import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const out = join(dirname(fileURLToPath(import.meta.url)), 'shots', 'brisa');
await mkdir(out, { recursive: true });
const erros = [];
const browser = await chromium.launch();

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  const tag = viewport.width;
  const page = await (await browser.newContext({ viewport, colorScheme: 'dark' })).newPage();
  page.on('pageerror', (e) => erros.push(`${tag} pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error') erros.push(`${tag} console: ${m.text()}`); });
  await page.goto('http://localhost:5173/lab/ui');
  await page.getByRole('heading', { name: 'Componentes base' }).waitFor();
  await page.waitForTimeout(800);
  await page.screenshot({ path: join(out, `${tag}-catalogo.png`), fullPage: true });
  const largura = await page.evaluate(() => document.documentElement.scrollWidth);
  if (largura > viewport.width) erros.push(`${tag}: rolagem horizontal (${largura}px)`);
  if (tag !== 1440) continue;

  // Tooltip pelo teclado: foco → aparece e liga aria-describedby; Esc → some
  const alvo = page.getByRole('button', { name: 'Passe o mouse ou foque' });
  await alvo.scrollIntoViewIfNeeded();
  await page.keyboard.press('Tab'); // garante modo teclado (:focus-visible)
  await alvo.focus();
  await page.waitForTimeout(200);
  const tip = page.getByRole('tooltip');
  if (!(await tip.isVisible())) erros.push('tooltip não abriu no foco');
  const desc = await alvo.getAttribute('aria-describedby');
  if (!desc || desc !== (await tip.getAttribute('id'))) erros.push(`aria-describedby errado: ${desc}`);
  await page.screenshot({ path: join(out, `${tag}-tooltip.png`) });
  await page.keyboard.press('Escape');
  await page.waitForTimeout(100);
  if (await tip.count()) erros.push('tooltip não fechou com Esc');

  // Toasts: fila de até 3, região aria-live, ação Desfazer
  for (const n of ['Neutro', 'Aviso', 'Sucesso com Desfazer', 'Erro (fica até fechar)']) await page.getByRole('button', { name: n, exact: true }).click();
  await page.waitForTimeout(300);
  const visiveis = await page.locator('.b-toast').count();
  if (visiveis !== 3) erros.push(`esperava 3 toasts visíveis, vieram ${visiveis}`);
  if (!(await page.locator('[role="alert"][aria-live="assertive"] .b-toast').count())) erros.push('toast de erro fora da região assertive');
  await page.screenshot({ path: join(out, `${tag}-toasts.png`) });
  await page.locator('.b-toast__acao', { hasText: 'Desfazer' }).click();
  await page.waitForTimeout(300);
  if (!(await page.getByText('Projeto restaurado').count())) erros.push('Desfazer não disparou a ação');
  if (await page.evaluate(() => document.activeElement?.closest('.b-toast'))) erros.push('toast roubou o foco');

  // Botão carregando: desativado + aria-busy + Sora pensando (canvas) no lugar do ícone
  const carregar = page.getByRole('button', { name: 'Clique para carregar' });
  await carregar.click();
  await page.waitForTimeout(150);
  const busy = page.locator('button[aria-busy="true"]', { hasText: 'Sora está criando…' });
  if (!(await busy.isDisabled()) || !(await busy.locator('canvas').count())) erros.push('estado carregando incompleto');
  await busy.screenshot({ path: join(out, `${tag}-carregando.png`) });
}
await browser.close();
console.log(erros.length ? `ERROS:\n${erros.join('\n')}` : 'OK sem erros');
