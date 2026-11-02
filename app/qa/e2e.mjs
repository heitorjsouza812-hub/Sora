// Fase C: fluxo real app -> API -> Redis/ARQ worker -> SSE -> revisão.
import assert from 'node:assert/strict';
import { mkdir, readdir, rm, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { entrarNoContexto } from './entrar.mjs';

const BASE = process.env.SORA_QA_BASE ?? 'http://localhost:5173';
const qaDir = dirname(fileURLToPath(import.meta.url));
const shots = join(qaDir, 'shots');
const consoleEvents = [];

function observar(page, viewport) {
  page.on('console', m => { if (m.type() === 'error') consoleEvents.push({ viewport, tipo: 'console', texto: m.text(), url: page.url() }); });
  page.on('pageerror', e => consoleEvents.push({ viewport, tipo: 'pageerror', texto: e.message, url: page.url() }));
}

async function screenshot(page, nome) { await page.screenshot({ path: join(shots, `e2e-${nome}.png`), fullPage: false }); }
async function visivel(page, texto, timeout = 20_000) { const alvo = page.getByText(texto, { exact: false }).first(); await alvo.waitFor({ state: 'visible', timeout }); return alvo; }

await mkdir(shots, { recursive: true });
await Promise.all((await readdir(shots)).filter(a => a.startsWith('e2e-') && a.endsWith('.png')).map(a => rm(join(shots, a))));

const browser = await chromium.launch({ headless: true });
const contexto = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' });
await entrarNoContexto(contexto);
const page = await contexto.newPage();
observar(page, '1440x900');

let falha;
try {
  const resposta = await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 30_000 });
  assert.ok(resposta?.ok(), 'a Home deve responder 2xx');
  await page.getByRole('textbox', { name: /Peça qualquer coisa à Sora/i }).waitFor({ state: 'visible', timeout: 15_000 });
  await screenshot(page, '01-inicio-1440x900');

  await page.getByRole('textbox', { name: /Peça qualquer coisa à Sora/i }).fill('crie uma campanha para minha cafeteria');
  await page.getByRole('button', { name: 'Enviar mensagem', exact: true }).click();
  await page.waitForURL(/\/projeto\//, { timeout: 30_000 });
  await visivel(page, 'Plano', 30_000);
  await visivel(page, 'Equipe', 30_000);
  await screenshot(page, '02-plano-equipe-1440x900');

  const abaTrabalho = page.getByRole('tab', { name: /Trabalho/ }).first();
  await abaTrabalho.waitFor({ state: 'visible', timeout: 30_000 });
  await abaTrabalho.click();
  await page.locator('.wk-panel').waitFor({ state: 'visible', timeout: 20_000 });
  // O modelo falso (SORA_MODELO_FALSO=1) só entrega; eventos `passo` vêm do caminho do modelo real
  // (middleware de passos). Por isso o painel precisa mostrar o agente e o progresso reais; os passos
  // (.wk-prompt/.wk-tool/.wk-step) entram só se o backend os emitir.
  await page.locator('.wk-head').first().waitFor({ state: 'visible', timeout: 60_000 });
  const passosNoPainel = await page.locator('.wk-prompt, .wk-tool, .wk-step').count();
  console.log(`Trabalho: ${passosNoPainel} passo(s) emitidos pelo backend neste fluxo.`);
  await screenshot(page, '03-trabalho-sse-1440x900');

  await page.getByRole('button', { name: 'Revisar', exact: true }).waitFor({ state: 'visible', timeout: 120_000 });
  await screenshot(page, '04-pronto-1440x900');

  const url = page.url();
  await page.reload({ waitUntil: 'domcontentloaded' });
  assert.equal(page.url(), url, 'recarregar deve manter a conversa real');
  await visivel(page, 'Plano', 30_000);
  await page.getByRole('button', { name: 'Revisar', exact: true }).waitFor({ state: 'visible', timeout: 30_000 });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(300);
  const largura = await page.evaluate(() => ({ pagina: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth }));
  assert.ok(largura.pagina <= largura.viewport, `chat real não pode rolar na horizontal (${largura.pagina}/${largura.viewport})`);
  await screenshot(page, '05-pronto-390x844');

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole('button', { name: 'Revisar', exact: true }).click();
  await page.getByRole('button', { name: /Aprovar e publicar/i }).waitFor({ state: 'visible', timeout: 20_000 });
  await screenshot(page, '06-revisao-1440x900');

  assert.deepEqual(consoleEvents, [], `console limpo:\n${JSON.stringify(consoleEvents, null, 2)}`);
} catch (erro) {
  falha = erro;
  try { await screenshot(page, 'FALHA'); } catch { /* página encerrada */ }
} finally {
  await writeFile(join(shots, 'e2e-console.json'), `${JSON.stringify(consoleEvents, null, 2)}\n`, 'utf8');
  await contexto.close();
  await browser.close();
}

if (falha || consoleEvents.length) {
  if (falha) console.error(`FALHA E2E real: ${falha.stack ?? falha.message}`);
  for (const erro of consoleEvents) console.error(`CONSOLE [${erro.viewport}] ${erro.texto}`);
  process.exitCode = 1;
} else {
  console.log('E2E real aprovado: campanha via backend/SSE, Trabalho, recarga, revisão e telas 1440/390; console limpo.');
}
