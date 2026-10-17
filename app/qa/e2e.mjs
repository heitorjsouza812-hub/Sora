import assert from 'node:assert/strict';
import { mkdir, readdir, rm, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { logarTodoContexto } from './entrar.mjs';

const BASE = 'http://localhost:5173';
const qaDir = dirname(fileURLToPath(import.meta.url));
const shots = join(qaDir, 'shots');
const consoleEvents = [];
// Erros 4xx da API que o cenário provoca de propósito (ex.: chave falsa → 422) não contam como erro de console.
let api4xxEsperado = false;
const failures = [];
let shotNo = 0;

const sleep = (page, ms) => page.waitForTimeout(ms);
const name = (text) => new RegExp(text, 'i');

function observe(page, viewport) {
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    if (api4xxEsperado && /Failed to load resource: the server responded with a status of 4\d\d/.test(message.text())) return;
    consoleEvents.push({ viewport, type: 'console', text: message.text(), url: page.url() });
  });
  page.on('pageerror', (error) => consoleEvents.push({ viewport, type: 'pageerror', text: error.message, url: page.url() }));
}

async function snap(page, label) {
  shotNo += 1;
  await page.screenshot({ path: join(shots, `e2e-${String(shotNo).padStart(2, '0')}-${label}.png`), fullPage: false });
}

async function goto(page, route) {
  const response = await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded', timeout: 30_000 });
  assert.ok(response?.ok(), `GET ${route} deveria responder 2xx`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(200);
}

async function reset(page) {
  await goto(page, '/');
  await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(250);
}

async function send(page, text) {
  const box = page.getByRole('textbox').last();
  await box.fill(text);
  await box.press('Enter');
}

async function expectVisible(page, text, timeout = 10_000) {
  const target = page.getByText(text, { exact: false }).first();
  await target.waitFor({ state: 'visible', timeout });
  return target;
}

async function menuAction(page, owner, action) {
  const row = page.locator(owner).first();
  await row.getByRole('button', { name: /opções/i }).click();
  await page.getByRole('menuitem', { name: action, exact: true }).click();
}

async function scenario(label, fn) {
  try {
    await fn();
  } catch (error) {
    failures.push({ label, error: error instanceof Error ? error.message : String(error) });
  }
}

async function rootInitial(page) {
  await reset(page);
  assert.equal(await page.getByText('Chats', { exact: true }).count(), 0, 'novo chat não deve listar CHATS');
  const heroOrbs = page.locator('.home-screen .hero-orb canvas');
  assert.equal(await heroOrbs.count(), 1, 'a home deve montar exatamente uma Sora no bloco principal');
  const heroBox = await heroOrbs.first().boundingBox();
  assert.ok(heroBox && heroBox.width >= 150 && heroBox.height >= 150, 'a Sora inicial deve ser grande (mínimo 150 px)');
  // Outros canvases de efeitos só são aceitáveis se não forem uma segunda Sora na hero.
  assert.equal(await page.locator('.home-screen .hero-orb canvas:visible').count(), 1, 'não deve haver duas Soras visíveis na hero');
  await snap(page, 'a-inicio');
}

async function flowAndReview(page) {
  await reset(page);

  await send(page, 'Crie uma campanha para lançar minha cafeteria');
  await expectVisible(page, 'Analisando o pedido');
  await expectVisible(page, 'Chats');
  await snap(page, 'a-pensando');

  await expectVisible(page, 'Plano', 8_000);
  await expectVisible(page, 'Definindo agente', 8_000);
  await expectVisible(page, 'Equipe', 8_000);
  await expectVisible(page, 'Trabalho', 12_000);
  await snap(page, 'a-plano-agentes');

  const reloadUrl = page.url();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle');
  assert.equal(page.url(), reloadUrl, 'recarregar no fluxo deve manter a rota do projeto');
  await expectVisible(page, 'Plano', 8_000);
  await snap(page, 'g-reload');

  await page.getByRole('tab', { name: /Trabalho/ }).first().click();
  await expectVisible(page, 'Sora pediu', 12_000);
  const tool = page.locator('.wk-tool').first();
  await tool.waitFor({ state: 'visible', timeout: 12_000 });
  const paramsBefore = await tool.locator('.wk-params-full').count();
  await tool.getByRole('button').click();
  await assert.doesNotReject(() => tool.locator('.wk-params-full').waitFor({ state: 'visible', timeout: 3_000 }), 'parâmetros da ferramenta devem expandir');
  assert.equal(paramsBefore, 0, 'parâmetros devem começar recolhidos');
  await snap(page, 'e-trabalho-parametros');

  await expectVisible(page, 'Revisar', 90_000);
  await page.getByRole('button', { name: 'Revisar', exact: true }).click();
  await expectVisible(page, 'Aprovar e publicar', 10_000);
  await page.getByRole('button', { name: 'Aprovar e publicar', exact: true }).click();
  await expectVisible(page, 'Aprovado', 5_000);
  await snap(page, 'a-aprovado');
}

async function ordinaryChat(page) {
  await reset(page);
  await send(page, 'oi, tudo bem?');
  await expectVisible(page, 'Oi', 6_000);
  assert.equal(await page.getByText('Equipe', { exact: true }).count(), 0, 'conversa comum não deve criar equipe');
  await snap(page, 'b-conversa-comum');
}

async function projects(page) {
  await reset(page);
  await goto(page, '/projetos');
  await send(page, 'Crie um projeto de campanha para uma padaria');
  await expectVisible(page, 'Plano', 10_000);
  await sleep(page, 6_000); // permite o nascimento dos agentes antes de testar a opção de mantê-los
  await goto(page, '/projetos');
  await expectVisible(page, 'Seus projetos');
  const card = page.locator('.pj-card').first();
  await card.waitFor({ state: 'visible', timeout: 5_000 });
  await menuAction(page, '.pj-card', 'Renomear');
  await page.getByLabel('Título').fill('Projeto Renomeado E2E');
  await page.getByRole('button', { name: 'Salvar', exact: true }).click();
  await expectVisible(page, 'Projeto Renomeado E2E');
  await snap(page, 'c-projeto-renomeado');

  await menuAction(page, '.pj-card', 'Apagar');
  await page.getByRole('checkbox', { name: 'Manter os agentes como avulsos' }).check();
  await page.getByRole('button', { name: 'Apagar', exact: true }).click();
  assert.equal(await page.getByText('Projeto Renomeado E2E', { exact: true }).count(), 0, 'projeto preservado deve sumir da lista');
  await goto(page, '/agentes');
  assert.ok(await page.locator('.agent-card, .ag-card, [class*=agent]').count() > 0, 'agentes preservados devem continuar em Agentes');

  await goto(page, '/projetos');
  await send(page, 'Crie um projeto de lançamento de uma loja');
  await expectVisible(page, 'Plano', 10_000);
  await goto(page, '/projetos');
  await menuAction(page, '.pj-card', 'Apagar');
  await page.getByRole('button', { name: 'Apagar', exact: true }).click();
  assert.equal(await page.locator('.pj-card').count(), 0, 'projeto apagado sem manter agentes deve sumir');
  await snap(page, 'c-projetos-apagados');
}

async function agents(page) {
  await reset(page);
  await goto(page, '/agentes/novo');
  await page.getByRole('tab', { name: 'Configurar', exact: true }).click();
  await page.getByText('Nome', { exact: true }).locator('..').getByRole('textbox').fill('Vigia E2E');
  await page.getByText('Função', { exact: true }).locator('..').getByRole('textbox').fill('Validação');
  await page.getByLabel('Cor hexadecimal').fill('#FF0069');
  await page.getByRole('button', { name: name('Ondas') }).click();
  await page.getByRole('button', { name: 'Criar agente', exact: true }).click();
  await expectVisible(page, 'Salvo');
  await sleep(page, 500); // aguarda a persistência agendada pelo store
  await goto(page, '/agentes');
  await expectVisible(page, 'Vigia E2E');
  await expectVisible(page, 'Chats');
  await snap(page, 'd-agente-criado');

  await page.getByRole('link', { name: 'Editar', exact: true }).first().click();
  await page.getByRole('tab', { name: 'Configurar', exact: true }).click();
  await page.getByLabel('Cor hexadecimal').fill('#00C4CC');
  await page.getByRole('button', { name: 'Salvar', exact: true }).click();
  await expectVisible(page, 'Salvo');
  await sleep(page, 400);
  await goto(page, '/');
  const customRow = page.locator('.chat-row').filter({ hasText: 'Vigia E2E' });
  await customRow.waitFor({ state: 'visible', timeout: 5_000 });
  const avatarColor = await customRow.evaluate((element) => getComputedStyle(element).getPropertyValue('--agent').trim());
  assert.match(avatarColor, /#00c4cc|rgb\(0,\s*196,\s*204\)/i, 'avatar da barra lateral deve receber a nova cor');

  await customRow.getByRole('button', { name: /opções/i }).click();
  // apagar agente é imediato, com toast "Desfazer" (item 45)
  await page.getByRole('menuitem', { name: 'Apagar', exact: true }).click();
  await expectVisible(page, 'Agente apagado', 3_000);
  assert.equal(await customRow.count(), 0, 'agente apagado não pode permanecer na barra lateral');
  await page.locator('.b-toast').filter({ hasText: 'Agente apagado' }).getByRole('button', { name: 'Desfazer', exact: true }).click();
  await customRow.waitFor({ state: 'visible', timeout: 3_000 });
  await customRow.getByRole('button', { name: /opções/i }).click();
  await page.getByRole('menuitem', { name: 'Apagar', exact: true }).click();
  await expectVisible(page, 'Agente apagado', 3_000);
  assert.equal(await customRow.count(), 0, 'agente apagado de novo não pode permanecer na barra lateral');
  await snap(page, 'd-agente-apagado');
}

async function settings(page) {
  await reset(page);
  await goto(page, '/configuracoes');
  // Etapa 2: o backend testa a chave antes de salvar; chave falsa → erro PT-BR e nada guardado no navegador.
  const card = page.locator('.cfg-provider-card').filter({ has: page.getByRole('button', { name: /OpenAI/i }) }).first();
  await card.getByRole('button', { name: /OpenAI/i }).click();
  await card.getByLabel('Chave da API').fill('sk-teste123');
  api4xxEsperado = true;
  await card.getByRole('button', { name: 'Testar e conectar', exact: true }).click();
  const retorno = card.locator('.cfg-card-feedback');
  await page.waitForFunction((el) => el && el.textContent.trim() && !el.textContent.includes('Falando com o servidor'), await retorno.elementHandle(), { timeout: 30_000 });
  const textoRetorno = (await retorno.innerText()).trim();
  assert.ok(!/conectada e modelos/i.test(textoRetorno), `chave falsa não pode conectar (retorno: ${textoRetorno})`);
  await expectVisible(page, 'Não conectado');
  const armazenado = await page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }));
  assert.ok(!armazenado.includes('sk-teste123'), 'nenhuma chave de API pode ficar no navegador');
  api4xxEsperado = false;
  await snap(page, 'f-configuracoes');
}

async function mobile(browser) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: 'dark' });
  const page = await context.newPage();
  observe(page, '390x844');
  try {
    await reset(page);
    const menu = page.getByRole('button', { name: 'Abrir menu', exact: true });
    await menu.click();
    await expectVisible(page, 'Menu');
    assert.equal(await menu.getAttribute('aria-expanded'), 'true');
    await page.keyboard.press('Escape');
    await page.waitForTimeout(150);
    assert.equal(await menu.getAttribute('aria-expanded'), 'false');
    for (const route of ['/', '/projetos', '/agentes', '/configuracoes', '/plugins']) {
      await goto(page, route);
      const metrics = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
      assert.ok(metrics.sw <= metrics.cw, `${route} não pode ter scroll horizontal (${metrics.sw}/${metrics.cw})`);
    }
    await snap(page, 'h-mobile');
  } finally {
    await context.close();
  }
}

await mkdir(shots, { recursive: true });
await Promise.all((await readdir(shots)).filter((file) => file.startsWith('e2e-') && file.endsWith('.png')).map((file) => rm(join(shots, file))));
const browser = logarTodoContexto(await chromium.launch({ headless: true }));
const desktopContext = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' });
const desktop = await desktopContext.newPage();
observe(desktop, '1440x900');
try {
  await scenario('a início sem chats e sem mascote', () => rootInitial(desktop));
  await scenario('a/e/g fluxo, trabalho, recarga e revisão', () => flowAndReview(desktop));
  await scenario('b conversa comum', () => ordinaryChat(desktop));
  await scenario('c projetos', () => projects(desktop));
  await scenario('d agentes', () => agents(desktop));
  await scenario('f configurações', () => settings(desktop));
  await scenario('h mobile', () => mobile(browser));
} finally {
  await desktopContext.close();
  await browser.close();
}
await writeFile(join(shots, 'e2e-console.json'), `${JSON.stringify({ consoleEvents, failures }, null, 2)}\n`, 'utf8');
if (failures.length || consoleEvents.length) {
  for (const failure of failures) console.error(`FALHA [${failure.label}]: ${failure.error}`);
  for (const entry of consoleEvents) console.error(`CONSOLE [${entry.viewport}]: ${entry.text}`);
  process.exitCode = 1;
} else {
  console.log(`E2E aprovado: ${shotNo} screenshots, sem erros de console.`);
}
