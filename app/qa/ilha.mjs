// Fase C: a Ilha deve refletir o stream agregado real, sem semear o store/localStorage.
import assert from 'node:assert/strict';
import { mkdir, readdir, rm } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { entrarNoContexto } from './entrar.mjs';

const BASE = process.env.SORA_QA_BASE ?? 'http://localhost:5173';
const qaDir = dirname(fileURLToPath(import.meta.url));
const shotsDir = join(qaDir, 'shots', 'ilha');
const erros = [];

await mkdir(shotsDir, { recursive: true });
await Promise.all((await readdir(shotsDir)).filter(a => a.endsWith('.png')).map(a => rm(join(shotsDir, a))));

const browser = await chromium.launch({ headless: true });
const contexto = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' });
await entrarNoContexto(contexto);
const page = await contexto.newPage();
page.on('console', m => { if (m.type() === 'error') erros.push({ tipo: 'console', texto: m.text(), url: page.url() }); });
page.on('pageerror', e => erros.push({ tipo: 'pageerror', texto: e.message, url: page.url() }));
const snap = nome => page.screenshot({ path: join(shotsDir, nome), fullPage: false });

let falha;
try {
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 30_000 });
  const compositor = page.getByRole('textbox', { name: /Peça qualquer coisa à Sora/i });
  await compositor.waitFor({ state: 'visible', timeout: 15_000 });
  await compositor.fill('crie uma campanha para lançar minha cafeteria');
  await page.getByRole('button', { name: 'Enviar mensagem', exact: true }).click();
  await page.waitForURL(/\/projeto\//, { timeout: 30_000 });

  const pilula = page.getByRole('button', { name: /^Ilha da Sora:/i });
  await pilula.waitFor({ state: 'visible', timeout: 30_000 });
  await snap('01-compacta-real-1440x900.png');
  await pilula.click();

  const ilha = page.getByRole('dialog', { name: 'Ilha da Sora', exact: true });
  await ilha.waitFor({ state: 'visible', timeout: 10_000 });
  // O modelo falso conclui a equipe em segundos: a ilha pode abrir direto na Aprovação. Confere e vai ao Início.
  await ilha.getByText(/A equipe terminou/i).waitFor({ state: 'visible', timeout: 120_000 });
  await snap('05-aprovacao-real-1440x900.png');
  await ilha.getByRole('button', { name: 'Início', exact: true }).click();
  await ilha.getByRole('button', { name: /Ver detalhes$/i }).first().waitFor({ state: 'visible', timeout: 45_000 });
  await snap('02-agentes-sse-1440x900.png');

  const filtro = ilha.getByRole('radiogroup', { name: 'Filtrar agentes', exact: true });
  await filtro.waitFor({ state: 'visible', timeout: 10_000 });
  const trabalhando = filtro.getByRole('radio', { name: /^Trabalhando\b/i });
  await trabalhando.click();
  assert.equal(await trabalhando.getAttribute('aria-checked'), 'true', 'filtro Trabalhando deve usar o estado SSE');
  await snap('03-filtro-real-1440x900.png');
  await filtro.getByRole('radio', { name: /^Todos\b/i }).click();

  await ilha.getByRole('button', { name: /Ver detalhes$/i }).first().click();
  await ilha.getByRole('button', { name: 'Abrir chat do agente', exact: true }).waitFor({ state: 'visible', timeout: 10_000 });
  await snap('04-detalhe-real-1440x900.png');


  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(300);
  const largura = await page.evaluate(() => ({ pagina: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth }));
  assert.ok(largura.pagina <= largura.viewport, `a Ilha real não pode causar rolagem horizontal (${largura.pagina}/${largura.viewport})`);
  await snap('06-aprovacao-real-390x844.png');
  assert.deepEqual(erros, [], `console limpo:\n${JSON.stringify(erros, null, 2)}`);
} catch (erro) {
  falha = erro;
  try { await snap('FALHA.png'); } catch { /* página encerrada */ }
} finally {
  await contexto.close();
  await browser.close();
}

if (falha || erros.length) {
  if (falha) console.error(`FALHA Ilha real: ${falha.stack ?? falha.message}`);
  for (const erro of erros) console.error(`CONSOLE [${erro.tipo}] ${erro.texto}`);
  process.exitCode = 1;
} else {
  console.log('Ilha real aprovada: stream agregado, filtro, detalhe, aprovação e telas 1440/390; console limpo.');
}
