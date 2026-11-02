// Fase C: fluxo real app -> API -> Redis/ARQ worker -> SSE -> revisão.
import assert from 'node:assert/strict';
import { mkdir, readdir, rm, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
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
  // Desde a rodada 4 o backend emite `passo` também com o modelo falso: o painel precisa mostrar
  // o agente, o progresso e pelo menos uma chamada de ferramenta real.
  await page.locator('.wk-head').first().waitFor({ state: 'visible', timeout: 60_000 });
  // O painel segue o agente que está trabalhando; espera por contagem, não por um elemento específico.
  await page.waitForFunction(() => document.querySelectorAll('.wk-prompt, .wk-tool, .wk-step').length >= 1, null, { timeout: 60_000 });
  await screenshot(page, '03-trabalho-sse-1440x900');

  await page.getByRole('button', { name: 'Revisar', exact: true }).waitFor({ state: 'visible', timeout: 120_000 });
  await screenshot(page, '04-pronto-1440x900');

  const url = page.url();
  const urlDoProjeto = url;
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

  // ── Pedido de ajuste: nova versão e comparação ────────────────────────────────────────────
  await page.getByRole('button', { name: 'Pedir ajuste', exact: true }).click();
  await page.getByRole('textbox', { name: /Instrução/i }).fill('deixe os textos mais descontraídos');
  await page.getByRole('button', { name: 'Enviar ajuste', exact: true }).click();
  await page.waitForURL(/\/projeto\//, { timeout: 20_000 });
  await page.locator('.version-compare').waitFor({ state: 'visible', timeout: 120_000 });
  await visivel(page, 'Versão anterior', 5_000);
  await visivel(page, 'Nova versão', 5_000);
  await screenshot(page, '07-ajuste-comparacao-1440x900');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(300);
  const largura2 = await page.evaluate(() => ({ pagina: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth }));
  assert.ok(largura2.pagina <= largura2.viewport, `comparação de versões não pode rolar na horizontal (${largura2.pagina}/${largura2.viewport})`);
  await screenshot(page, '08-ajuste-comparacao-390x844');
  await page.setViewportSize({ width: 1440, height: 900 });

  // ── Resposta direta: "oi" não monta plano nem equipe ──────────────────────────────────────
  await page.getByRole('link', { name: 'Novo chat', exact: true }).click();
  const campo = page.getByRole('textbox', { name: /Peça qualquer coisa à Sora/i });
  await campo.waitFor({ state: 'visible', timeout: 15_000 });
  await campo.fill('oi');
  await page.getByRole('button', { name: 'Enviar mensagem', exact: true }).click();
  await page.waitForURL(/\/projeto\//, { timeout: 30_000 });
  await page.waitForFunction(() => document.querySelectorAll('.chat-item').length >= 2, null, { timeout: 60_000 });
  await page.waitForTimeout(3_000);
  assert.equal(await page.getByText(/^Plano ·/).count(), 0, 'resposta direta não monta plano');
  assert.equal(await page.getByRole('button', { name: 'Revisar', exact: true }).count(), 0, 'resposta direta não pede revisão');
  await screenshot(page, '09-resposta-direta-1440x900');

  // ── Cartões de pergunta e de aprovação ───────────────────────────────────────────────────
  // O modelo falso nunca pergunta nem pede aprovação: qa/injetar-pendencia.py grava a linha e publica o
  // evento como o motor faria; a resposta do usuário passa pelas rotas reais. A retomada da cadeia depois
  // da resposta NÃO é coberta aqui (precisa de modelo que chame perguntar/criar_agente).
  await page.goto(urlDoProjeto);
  await page.getByRole('button', { name: 'Revisar', exact: true }).waitFor({ state: 'visible', timeout: 30_000 });
  const conversaId = page.url().split('/').pop();
  const injetar = (...args) => {
    const r = spawnSync('uv', ['run', 'python', join(qaDir, 'injetar-pendencia.py'), ...args], { cwd: join(qaDir, '..', '..', 'backend'), env: process.env, encoding: 'utf8', shell: process.platform === 'win32' });
    assert.equal(r.status, 0, `injetar-pendencia ${args.join(' ')}: ${r.stderr}`);
    return r.stdout.trim().split('\n').pop();
  };
  const fecharIlha = async () => { await page.keyboard.press('Escape'); await page.waitForTimeout(400); };

  // pergunta com opções + resposta livre
  const perguntaId = injetar('pergunta', conversaId);
  const cartaoPergunta = page.locator('[data-pendencia="pergunta"]').first();
  await cartaoPergunta.waitFor({ state: 'visible', timeout: 20_000 });
  await visivel(page, 'A equipe precisa de você', 5_000);
  await visivel(page, 'Aguardando você', 5_000);
  await screenshot(page, '11-pergunta-1440x900');
  await fecharIlha();
  await cartaoPergunta.getByRole('button', { name: 'Clientes novos', exact: true }).click();
  await cartaoPergunta.waitFor({ state: 'detached', timeout: 15_000 });
  assert.match(injetar('estado', perguntaId), /resposta='novos' respondida=True/, 'a resposta precisa ter sido gravada pela rota real');

  // orçamento estourado: pergunta Continuar/Parar
  const orcamentoId = injetar('pergunta', conversaId, '--orcamento');
  const cartaoOrcamento = page.locator('[data-pendencia="pergunta"]').first();
  await cartaoOrcamento.waitFor({ state: 'visible', timeout: 20_000 });
  await fecharIlha();
  await cartaoOrcamento.getByRole('button', { name: 'Continuar', exact: true }).waitFor({ state: 'visible' });
  await cartaoOrcamento.getByRole('button', { name: 'Parar', exact: true }).waitFor({ state: 'visible' });
  await cartaoOrcamento.getByRole('button', { name: 'Continuar', exact: true }).click();
  await cartaoOrcamento.waitFor({ state: 'detached', timeout: 15_000 });
  assert.match(injetar('estado', orcamentoId), /resposta='continuar'/);

  // aprovação de criar_agente
  const aprovacaoId = injetar('aprovacao', conversaId);
  const cartaoAprovacao = page.locator('[data-pendencia="aprovacao"]').first();
  await cartaoAprovacao.waitFor({ state: 'visible', timeout: 20_000 });
  await visivel(page, 'Criar o agente Íris', 5_000);
  await fecharIlha();
  await cartaoAprovacao.getByRole('button', { name: 'Recusar', exact: true }).waitFor({ state: 'visible' });
  await screenshot(page, '12-aprovacao-1440x900');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(300);
  const largura3 = await page.evaluate(() => ({ pagina: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth }));
  assert.ok(largura3.pagina <= largura3.viewport, `cartão de aprovação não pode rolar na horizontal (${largura3.pagina}/${largura3.viewport})`);
  await cartaoAprovacao.scrollIntoViewIfNeeded();
  await screenshot(page, '13-aprovacao-390x844');
  await page.setViewportSize({ width: 1440, height: 900 });
  await cartaoAprovacao.getByRole('button', { name: 'Aprovar', exact: true }).click();
  await cartaoAprovacao.waitFor({ state: 'detached', timeout: 15_000 });
  assert.match(injetar('estado', aprovacaoId), /status='?permitida/, 'a aprovação precisa ter sido gravada pela rota real');

  // ── Aviso de erro do provedor (precisa de API sem modelo falso: SORA_QA_BASE_ERRO) ────────
  if (process.env.SORA_QA_BASE_ERRO) {
    const r = spawnSync(process.execPath, [join(qaDir, 'e2e-erro-provedor.mjs')], { stdio: 'inherit', env: { ...process.env, SORA_QA_BASE: process.env.SORA_QA_BASE_ERRO } });
    assert.equal(r.status, 0, 'cenário de erro do provedor falhou');
  } else console.log('AVISO: SORA_QA_BASE_ERRO não definido; cenário de erro do provedor não executado.');

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
