// Seletor de modelo e permissão: fotos a 1440 e 390 px em qa/shots/seletor/ (conta de QA própria).
import { chromium } from '@playwright/test';
import { readFileSync, mkdirSync } from 'node:fs';
import { entrarNoContexto, BASE } from './entrar.mjs';
const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const email = `vitral12-${Date.now()}@sora.local`;
const dir = 'qa/shots/seletor'; mkdirSync(dir, { recursive: true });
try {
  const login = await entrarNoContexto(ctx, { email });
  const headers = { Authorization: `Bearer ${login.token_acesso}` };
  const env = readFileSync('../backend/.env', 'utf8');
  const chave = env.match(/^SORA_QA_GROQ_CHAVE\s*=\s*(.+)$/m)?.[1].trim().replace(/^['"]|['"]$/g, '');
  if (chave) await ctx.request.post(`${BASE}/v1/provedores`, { headers, data: { tipo: 'groq', chave } });
  const modelos = await (await ctx.request.get(`${BASE}/v1/modelos`, { headers })).json();
  console.log('modelos', modelos.length, JSON.stringify(modelos[0] ?? null).slice(0, 300));
  const rotas = await ctx.request.get(`${BASE}/v1/conversas/x/preferencias`, { headers });
  console.log('GET preferencias →', rotas.status());
  const page = await ctx.newPage();
  page.on('console', m => { if (m.type() === 'error') console.log('console:', m.text().slice(0, 200)); });
  for (const [w, h, nome] of [[1440, 900, '1440'], [390, 844, '390']]) {
    await page.setViewportSize({ width: w, height: h });
    await page.goto(BASE); await page.waitForTimeout(1500);
    await page.screenshot({ path: `${dir}/sora-fechado-${nome}.png` });
    await page.getByRole('button', { name: /Automático|⌄/ }).first().click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${dir}/sora-aberto-${nome}.png` });
    await page.keyboard.press('Escape');
    await page.goto(`${BASE}/bots/novo`); await page.waitForTimeout(1500);
    await page.screenshot({ path: `${dir}/novo-bot-${nome}.png`, fullPage: true });
    await page.getByRole('button', { name: /Monitorar preços/ }).click();
    console.log(nome, 'campo preenchido:', await page.getByRole('textbox').inputValue(), '| URL', page.url());
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${BASE}/bots/novo`);
  await page.getByRole('button', { name: /Automático|⌄/ }).first().click();
  await page.getByLabel('Permissão', { exact: true }).selectOption('total');
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${dir}/acesso-total-dialogo-1440.png` });
} finally { await ctx.close(); await browser.close(); }
