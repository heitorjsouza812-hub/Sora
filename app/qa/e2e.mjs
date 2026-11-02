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
const streams429 = [];

function observar(page, viewport) {
  // Um 429 em /v1/*/eventos é regressão: o servidor deve liberar a vaga ao notar a desconexão.
  page.on('response', r => { if (r.status() === 429 && r.url().includes('/eventos')) streams429.push(r.url()); });
  page.on('console', m => {
    if (m.type() !== 'error') return;
    consoleEvents.push({ viewport, tipo: 'console', texto: m.text(), url: page.url() });
  });
  page.on('pageerror', e => consoleEvents.push({ viewport, tipo: 'pageerror', texto: e.message, url: page.url() }));
}

async function screenshot(page, nome) { await page.screenshot({ path: join(shots, `e2e-${nome}.png`), fullPage: false }); }
async function visivel(page, texto, timeout = 20_000) { const alvo = page.getByText(texto, { exact: false }).first(); await alvo.waitFor({ state: 'visible', timeout }); return alvo; }

await mkdir(shots, { recursive: true });
await Promise.all((await readdir(shots)).filter(a => a.startsWith('e2e-') && a.endsWith('.png')).map(a => rm(join(shots, a))));

const browser = await chromium.launch({ headless: true });
const contexto = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' });
await entrarNoContexto(contexto, {
  email: process.env.SORA_QA_E2E_EMAIL ?? 'qa-e2e@sora.local',
  limparConversas: true,
});
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
  for (let recarga = 0; recarga < 6; recarga += 1) {
    await page.reload({ waitUntil: 'domcontentloaded' });
    assert.equal(page.url(), url, 'recarregar deve manter a conversa real');
    await page.waitForTimeout(1_200);
  }
  await visivel(page, 'Plano', 30_000);
  await page.getByRole('button', { name: 'Revisar', exact: true }).waitFor({ state: 'visible', timeout: 30_000 });
  assert.deepEqual(streams429, [], `recargas não podem esgotar streams SSE:\n${streams429.join('\n')}`);
  assert.equal(await page.getByText(/Atualizações ao vivo pausadas/i).count(), 0, 'o aviso de limite SSE não deve aparecer');

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

  // ── Gatilhos do modelo falso: pergunta, aprovação, orçamento (Continuar e Parar) ─────────────
  // Fluxo completo pelo app: envia o pedido com a tag, responde no cartão (chat ou ilha) e confere o fim
  // da cadeia. Tags: [pergunta], [aprovacao], [orcamento] (.maestri/contrato-etapa3.md, rodada 4).
  const fecharIlha = async () => { await page.keyboard.press('Escape'); await page.waitForTimeout(400); };
  const enviarPedido = async (texto) => {
    await page.getByRole('link', { name: 'Novo chat', exact: true }).click();
    const campo = page.getByRole('textbox', { name: /Peça qualquer coisa à Sora/i });
    await campo.waitFor({ state: 'visible', timeout: 15_000 });
    await campo.fill(texto);
    await page.getByRole('button', { name: 'Enviar mensagem', exact: true }).click();
    await page.waitForURL(/\/projeto\//, { timeout: 30_000 });
  };
  const concluiu = async () => {
    await page.getByRole('button', { name: 'Revisar', exact: true }).waitFor({ state: 'visible', timeout: 120_000 });
    assert.equal(await page.locator('[data-pendencia]').count(), 0, 'depois de concluir não pode sobrar cartão');
  };

  // [pergunta]: responde no cartão do chat
  await enviarPedido('crie uma campanha para minha cafeteria [pergunta]');
  const cartaoPergunta = page.locator('[data-pendencia="pergunta"]').first();
  await cartaoPergunta.waitFor({ state: 'visible', timeout: 90_000 });
  await visivel(page, 'A equipe precisa de você', 5_000);
  await visivel(page, 'Aguardando você', 5_000);
  await page.waitForTimeout(1_000);
  await screenshot(page, '11-pergunta-1440x900');
  await fecharIlha();
  const opcaoEscolhida = await cartaoPergunta.getByRole('button').first().innerText();
  await cartaoPergunta.getByRole('button').first().click();
  await cartaoPergunta.waitFor({ state: 'detached', timeout: 15_000 });
  await concluiu();
  console.log(`[pergunta] respondida com "${opcaoEscolhida}" e a cadeia concluiu.`);

  // [aprovacao] recusada (primeiro: o fake sempre cria "Organizadora" e, existindo, não pede de novo): negar
  // não trava a cadeia e não cria agente
  await enviarPedido('crie uma campanha para minha cafeteria [aprovacao]');
  const cartaoRecusa = page.locator('[data-pendencia="aprovacao"]').first();
  await cartaoRecusa.waitFor({ state: 'visible', timeout: 90_000 });
  await fecharIlha();
  await cartaoRecusa.getByRole('button', { name: 'Recusar', exact: true }).click();
  await cartaoRecusa.waitFor({ state: 'detached', timeout: 15_000 });
  await concluiu();
  assert.equal(await page.locator('aside.sidebar').getByText('Organizadora').count(), 0, 'recusar não cria agente');
  console.log('[aprovacao] recusada: a cadeia concluiu e nenhum agente foi criado.');


  // [aprovacao]: decide no cartão da ILHA (abre sozinha); o agente criado aparece em CHATS
  await enviarPedido('crie uma campanha para minha cafeteria [aprovacao]');
  const ilhaDialogo = page.getByRole('dialog', { name: 'Ilha da Sora', exact: true });
  const cartaoNaIlha = ilhaDialogo.locator('[data-pendencia="aprovacao"]');
  await cartaoNaIlha.waitFor({ state: 'visible', timeout: 90_000 });
  await visivel(page, 'Organizadora', 5_000);
  await page.waitForTimeout(1_000);
  await screenshot(page, '12-aprovacao-ilha-1440x900');
  await cartaoNaIlha.getByRole('button', { name: 'Aprovar', exact: true }).click();
  await cartaoNaIlha.waitFor({ state: 'detached', timeout: 15_000 });
  await fecharIlha();
  await concluiu();
  // o agente individual criado pela aprovação aparece solto em CHATS (se o evento não o trouxe, a recarga traz)
  const naBarra = page.locator('aside.sidebar').getByText('Organizadora').first();
  // a pasta do projeto atual (a 1ª, a mais recente) começa recolhida: abre e exige o agente visível
  const pasta = page.locator('aside.sidebar .pasta-toggle').first();
  await pasta.waitFor({ state: 'visible', timeout: 15_000 });
  if ((await pasta.getAttribute('aria-expanded')) !== 'true') await pasta.click();
  await naBarra.waitFor({ state: 'visible', timeout: 30_000 });
  await page.waitForTimeout(500);
  await fecharIlha();
  await screenshot(page, '13-agente-criado-chats-1440x900');
  console.log('[aprovacao] aprovada na ilha, cadeia concluída e "Organizadora" visível em CHATS.');

  // [orcamento] + Continuar
  await enviarPedido('crie uma campanha para minha cafeteria [orcamento]');
  const cartaoOrcamento = page.locator('[data-pendencia="pergunta"]').first();
  await cartaoOrcamento.waitFor({ state: 'visible', timeout: 90_000 });
  await fecharIlha();
  await cartaoOrcamento.getByRole('button', { name: 'Parar', exact: true }).waitFor({ state: 'visible' });
  await screenshot(page, '14-orcamento-1440x900');
  await cartaoOrcamento.getByRole('button', { name: 'Continuar', exact: true }).click();
  await cartaoOrcamento.waitFor({ state: 'detached', timeout: 15_000 });
  await concluiu();
  console.log('[orcamento] Continuar: a cadeia concluiu.');

  // [orcamento] + Parar: a etapa e a cadeia falham, sem cartão sobrando e sem "Revisar"
  await enviarPedido('crie uma campanha para minha cafeteria [orcamento]');
  const cartaoParar = page.locator('[data-pendencia="pergunta"]').first();
  await cartaoParar.waitFor({ state: 'visible', timeout: 90_000 });
  await fecharIlha();
  await cartaoParar.getByRole('button', { name: 'Parar', exact: true }).click();
  await cartaoParar.waitFor({ state: 'detached', timeout: 15_000 });
  await visivel(page, 'A equipe parou', 90_000);
  assert.equal(await page.getByRole('button', { name: 'Revisar', exact: true }).count(), 0, 'cadeia parada não pede revisão');
  assert.equal(await page.locator('[data-pendencia]').count(), 0);
  await screenshot(page, '15-orcamento-parar-1440x900');
  console.log('[orcamento] Parar: a cadeia falhou e o app mostra que a equipe parou.');

  // celular: cartão de pergunta sem rolagem horizontal
  await enviarPedido('crie uma campanha para minha cafeteria [pergunta]');
  const cartaoMovel = page.locator('[data-pendencia="pergunta"]').first();
  await cartaoMovel.waitFor({ state: 'visible', timeout: 90_000 });
  await fecharIlha();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(300);
  const largura3 = await page.evaluate(() => ({ pagina: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth }));
  assert.ok(largura3.pagina <= largura3.viewport, `cartão de pergunta não pode rolar na horizontal (${largura3.pagina}/${largura3.viewport})`);
  await cartaoMovel.scrollIntoViewIfNeeded();
  await screenshot(page, '16-pergunta-390x844');
  await cartaoMovel.getByRole('button').first().click();
  await cartaoMovel.waitFor({ state: 'detached', timeout: 15_000 });
  await concluiu();
  await page.setViewportSize({ width: 1440, height: 900 });

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
  console.log('E2E real aprovado: campanha via backend/SSE, seis recargas sem 429, Trabalho, revisão e telas 1440/390; console limpo.');
}
