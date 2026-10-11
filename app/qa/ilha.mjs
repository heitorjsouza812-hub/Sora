import assert from 'node:assert/strict';
import { mkdir, readdir, rm } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const BASE = 'http://localhost:5173';
const qaDir = dirname(fileURLToPath(import.meta.url));
const shotsDir = join(qaDir, 'shots', 'ilha');
const errosConsole = [];
let page;

function observarConsole(alvo) {
  alvo.on('console', (mensagem) => {
    if (mensagem.type() === 'error') {
      errosConsole.push({ tipo: 'console', texto: mensagem.text(), url: alvo.url() });
    }
  });
  alvo.on('pageerror', (erro) => {
    errosConsole.push({ tipo: 'pageerror', texto: erro.message, url: alvo.url() });
  });
}

async function screenshot(nome) {
  await page.screenshot({ path: join(shotsDir, nome), fullPage: false });
}

async function limparDados() {
  const resposta = await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 30_000 });
  assert.ok(resposta?.ok(), 'a Home deveria responder 2xx');
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await page.reload({ waitUntil: 'domcontentloaded' });
}

async function criarProjeto() {
  const compositor = page.getByRole('textbox', { name: /Peça qualquer coisa à Sora/i });
  await compositor.waitFor({ state: 'visible', timeout: 10_000 });
  await compositor.fill('crie uma campanha para lançar minha cafeteria');
  await page.getByRole('button', { name: 'Enviar mensagem', exact: true }).click();
  await page.waitForURL(/\/projeto\//, { timeout: 10_000 });
}

async function pilulaIlha() {
  const pilula = page.getByRole('button', { name: /^Ilha da Sora:/i });
  await pilula.waitFor({ state: 'visible', timeout: 15_000 });
  return pilula;
}

async function expandirIlha(pilula) {
  await pilula.click();
  const dialogo = page.getByRole('dialog', { name: 'Ilha da Sora', exact: true });
  await dialogo.waitFor({ state: 'visible', timeout: 5_000 });
  await dialogo.getByRole('button', { name: 'Fechar ilha', exact: true }).waitFor({ state: 'visible', timeout: 5_000 });
  return dialogo;
}

async function escolherProjeto(dialogo) {
  const navegacao = dialogo.getByRole('toolbar', { name: 'Navegação da ilha', exact: true });
  await navegacao.getByRole('button').nth(1).click();
  const lista = dialogo.getByRole('listbox', { name: 'Projetos', exact: true });
  await lista.waitFor({ state: 'visible', timeout: 5_000 });
  const projeto = lista.getByRole('option').filter({ hasNotText: /Automático/i }).first();
  await projeto.waitFor({ state: 'visible', timeout: 5_000 });
  await projeto.click();
  await dialogo.getByRole('button', { name: /Ver detalhes$/i }).first().waitFor({ state: 'visible', timeout: 20_000 });
}

async function abrirDetalheDoAgente(dialogo) {
  const agente = dialogo.getByRole('button', { name: /Ver detalhes$/i }).first();
  await agente.click();
  await dialogo.getByRole('button', { name: /Voltar/i }).waitFor({ state: 'visible', timeout: 5_000 });
  await dialogo.getByRole('button', { name: 'Abrir chat do agente', exact: true }).waitFor({ state: 'visible', timeout: 5_000 });
}

async function esperarAprovacao(dialogo) {
  await dialogo.getByText(/A equipe terminou/i).waitFor({ state: 'visible', timeout: 120_000 });
  await dialogo.getByRole('button', { name: /^Aprovar e publicar\b/i }).waitFor({ state: 'visible', timeout: 5_000 });
}

await mkdir(shotsDir, { recursive: true });
await Promise.all((await readdir(shotsDir)).filter((arquivo) => arquivo.endsWith('.png')).map((arquivo) => rm(join(shotsDir, arquivo))));

const browser = await chromium.launch({ headless: true });
const contexto = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' });
page = await contexto.newPage();
observarConsole(page);

let falha;
try {
  await limparDados();
  await criarProjeto();

  const pilula = await pilulaIlha();
  await screenshot('01-compacta-1440x900.png');

  const ilha = await expandirIlha(pilula);
  await screenshot('02-expandida-1440x900.png');

  await escolherProjeto(ilha);
  await abrirDetalheDoAgente(ilha);
  await screenshot('03-agente-1440x900.png');

  await esperarAprovacao(ilha);
  await screenshot('04-aprovacao-1440x900.png');

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(250);
  const largura = await page.evaluate(() => ({ pagina: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth }));
  assert.ok(largura.pagina <= largura.viewport, `a Ilha não pode causar rolagem horizontal no celular (${largura.pagina}/${largura.viewport})`);
  await screenshot('05-aprovacao-390x844.png');

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForTimeout(150);
  await ilha.getByRole('button', { name: /^Aprovar e publicar\b/i }).click();
  await page.getByText('Projeto aprovado e publicado', { exact: true }).waitFor({ state: 'visible', timeout: 5_000 });
  await screenshot('06-aprovado-1440x900.png');

  assert.deepEqual(errosConsole, [], `o console deveria ficar limpo:\n${JSON.stringify(errosConsole, null, 2)}`);
} catch (erro) {
  falha = erro;
  try { await screenshot('FALHA.png'); } catch { /* a página pode ter fechado */ }
} finally {
  await contexto.close();
  await browser.close();
}

if (falha || errosConsole.length) {
  if (falha) console.error(`FALHA Ilha: ${falha instanceof Error ? falha.stack ?? falha.message : String(falha)}`);
  for (const erro of errosConsole) console.error(`CONSOLE [${erro.tipo}] ${erro.texto} (${erro.url})`);
  process.exitCode = 1;
} else {
  console.log('Ilha aprovada: fluxo completo, 6 screenshots (1440x900 e 390x844), console limpo.');
}
