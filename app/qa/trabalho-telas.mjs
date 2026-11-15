// QA ao vivo (Vitral-8): painel Trabalho com tela do navegador e do computador do bot.
// API e Vite reais (bot criado pela API real); só as rotas de tela são simuladas com page.route, porque o worker
// de QA usa modelo falso e não abre navegador nem computador de verdade.
// Uso: node qa/trabalho-telas.mjs   (SORA_QA_BASE=http://localhost:5383)
import { readFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
import { BASE, entrarNoContexto } from './entrar.mjs';

const pasta = fileURLToPath(new URL('./shots/trabalho/', import.meta.url));
await mkdir(pasta, { recursive: true });
const foto = nome => `${pasta}${nome}.png`;
const png = await readFile(new URL('./shots/e2e-etapa5-01-sora.png', import.meta.url));
const browser = await chromium.launch({ headless: true });
let falhou = false;
try {
  const contexto = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const sessao = await entrarNoContexto(contexto);
  const auth = { Authorization: `Bearer ${sessao.token_acesso}` };
  const nome = `Tela ${Date.now().toString(36).slice(-4)}`;
  const criado = await contexto.request.post(`${BASE}/v1/agentes`, { headers: auth, data: { nome, funcao: 'QA de telas', papel: 'Testa as telas ao vivo', ferramentas: ['computador_observar', 'computador_agir', 'computador_desligar'] } });
  assert.equal(criado.status(), 201, await criado.text());
  const bot = await criado.json(); const id = bot.id;
  console.log('bot', id, bot.ferramentas);

  const abaId = 'aba-qa-1'; let assumida = false; const chamadas = []; let ligado = true;
  const aba = () => ({ aba_id: abaId, agente_id: id, url: 'https://exemplo.com.br/pedido', titulo: 'Pedido 1042', carregada: true, assumida_pelo_usuario: assumida });
  const json = (r, corpo, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(corpo) });
  const abrir = async (largura, altura, caminho) => {
    const page = await contexto.newPage(); await page.setViewportSize({ width: largura, height: altura });
    chamadas.length = 0; assumida = false; ligado = true;
    await page.route(/\/v1\/navegador\/abas(\?.*)?$/, r => json(r, [aba()]));
    await page.route(/\/v1\/navegador\/abas\/[^/]+\/captura/, r => r.fulfill({ status: 200, contentType: 'image/png', body: png }));
    await page.route(/\/v1\/navegador\/abas\/[^/]+\/(assumir|devolver|clicar|digitar|tecla|rolar)$/, r => {
      const acao = r.request().url().split('/').pop();
      chamadas.push({ acao, corpo: acao === 'digitar' ? '[texto]' : r.request().postData() });
      if (acao === 'assumir') assumida = true;
      if (acao === 'devolver') assumida = false;
      return json(r, acao === 'assumir' || acao === 'devolver' ? aba() : { enviado: true });
    });
    await page.route(/\/navegador\/assistir$/, r => { chamadas.push({ acao: 'assistir', t: Date.now() }); return json(r, { expira_em_segundos: 12 }); });
    await page.route(/\/v1\/agentes\/[^/]+\/computador$/, r => json(r, { agente_id: id, disponivel: true, ligado, alvo: 'docker', largura: 1280, altura: 800, janela_ativa: 'Planilha — contas.xlsx', acao: 'Abrindo a planilha', atualizado_em: new Date().toISOString() }));
    await page.route(/\/computador\/captura/, r => r.fulfill({ status: 200, contentType: 'image/png', body: png }));
    await page.route(/\/computador\/desligar$/, r => { chamadas.push({ acao: 'desligar' }); ligado = false; return json(r, {}, 202); });
    await page.route(/\/v1\/agentes\/[^/]+\/navegador$/, r => json(r, { agente_id: id, tipo: 'agente', perfil_id: null, perfil_nome: null }));
    await page.goto(`${BASE}${caminho}`, { waitUntil: 'domcontentloaded' });
    return page;
  };

  // ── 1440 ──
  let page = await abrir(1440, 900, `/bots/${id}`);
  await page.getByRole('tab', { name: 'Trabalho' }).click().catch(() => undefined);
  const nav = page.getByRole('region', { name: 'Navegador ao vivo' });
  await nav.waitFor({ state: 'visible', timeout: 20_000 });
  // Navegador e computador são abas (uma tela por vez): a aba "Computador" precisa existir.
  const abas = page.getByRole('tablist', { name: 'Telas do bot' });
  await abas.getByRole('tab', { name: 'Computador' }).waitFor({ state: 'visible' });
  await page.waitForTimeout(800);
  assert.ok(chamadas.some(c => c.acao === 'assistir'), 'manda assistir ao abrir');
  await page.screenshot({ path: foto('telas-1440-vendo') });
  await nav.getByRole('button', { name: 'Assumir a aba' }).click();
  await nav.getByText('Você está no controle — o bot espera.').waitFor();
  const img = nav.locator('img.wk-tela-img');
  await img.click({ position: { x: 40, y: 30 } });
  await nav.locator('.wk-tela-caixa').focus();
  await page.keyboard.type('abc'); await page.keyboard.press('Enter');
  await img.hover(); await page.mouse.wheel(0, 300); await page.waitForTimeout(700);
  await page.screenshot({ path: foto('telas-1440-assumida') });
  console.log('chamadas', JSON.stringify(chamadas.map(c => c.acao)));
  for (const a of ['assumir', 'clicar', 'digitar', 'tecla', 'rolar']) assert.ok(chamadas.some(c => c.acao === a), `faltou ${a}`);
  const clique = JSON.parse(chamadas.find(c => c.acao === 'clicar').corpo);
  assert.ok(clique.largura > 0 && clique.x >= 0 && clique.y >= 0, 'clique na escala da imagem');
  await nav.getByRole('button', { name: 'Ampliar' }).click();
  await page.getByRole('dialog').waitFor();
  await page.screenshot({ path: foto('telas-1440-ampliada') });
  await page.keyboard.press('Escape');
  await nav.getByRole('button', { name: 'Devolver ao bot' }).click();
  await nav.getByText('Devolvido. O bot retoma na próxima ação dele.').waitFor();
  await abas.getByRole('tab', { name: 'Computador' }).click();
  const pc = page.getByRole('region', { name: 'Computador do bot' });
  await pc.waitFor({ state: 'visible' });
  await pc.getByRole('button', { name: 'Desligar computador' }).click();
  await page.getByRole('dialog').waitFor();
  await page.screenshot({ path: foto('telas-1440-desligar') });
  assert.ok(!chamadas.some(c => c.acao === 'desligar'), 'não desliga antes de confirmar');
  await page.getByRole('dialog').getByRole('button', { name: 'Desligar', exact: true }).click();
  await page.waitForTimeout(500);
  assert.ok(chamadas.some(c => c.acao === 'desligar'), 'desliga ao confirmar');
  await abas.getByRole('tab', { name: 'Navegador' }).click();
  await nav.waitFor({ state: 'visible' });
  const antes = chamadas.filter(c => c.acao === 'assistir').length;
  await page.evaluate(() => { Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' }); document.dispatchEvent(new Event('visibilitychange')); });
  await page.waitForTimeout(9000);
  assert.equal(chamadas.filter(c => c.acao === 'assistir').length, antes, 'página escondida não manda assistir');
  await page.evaluate(() => { Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' }); document.dispatchEvent(new Event('visibilitychange')); });
  await page.waitForTimeout(600);
  assert.ok(chamadas.filter(c => c.acao === 'assistir').length > antes, 'volta a mandar ao ficar visível');
  await page.close();

  // ── 390 ──
  page = await abrir(390, 844, `/bots/${id}?painel=trabalho`);
  let nav2 = page.getByRole('region', { name: 'Navegador ao vivo' });
  if (!(await nav2.isVisible().catch(() => false))) {
    await page.getByRole('button', { name: /Ver trabalho|Ver passos/ }).first().click().catch(() => undefined);
    await page.getByRole('tab', { name: 'Trabalho' }).click().catch(() => undefined);
  }
  await nav2.waitFor({ state: 'visible', timeout: 20_000 });
  await nav2.getByRole('button', { name: 'Assumir a aba' }).click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: foto('telas-390-assumida') });
  const medidas = await page.evaluate(() => {
    const regiao = document.querySelector('.wk-tela'); const i = regiao.querySelector('img').getBoundingClientRect();
    const botoes = [...document.querySelectorAll('.wk-tela button')].map(b => ({ t: b.textContent, h: b.getBoundingClientRect().height, w: b.getBoundingClientRect().width }));
    return { vw: innerWidth, sw: document.documentElement.scrollWidth, imgDir: i.right, botoes };
  });
  console.log('390:', JSON.stringify(medidas));
  assert.ok(medidas.sw <= medidas.vw, 'sem rolagem horizontal');
  assert.ok(medidas.imgDir <= medidas.vw, 'imagem cabe na largura');
  for (const b of medidas.botoes) assert.ok(b.h >= 44 && b.w >= 44, `alvo pequeno: ${b.t} ${b.w}x${b.h}`);
  await page.close();

  // ── formulário do bot ──
  page = await abrir(1440, 900, `/agentes/${id}/editar`);
  const grupo = page.locator('summary', { hasText: 'Computador e navegador' });
  await grupo.waitFor({ timeout: 20_000 }); await grupo.click();
  await page.getByText('Computador próprio').waitFor();
  await page.screenshot({ path: foto('form-1440') });
  console.log('OK');
} catch (e) { falhou = true; console.error(e); } finally { await browser.close(); }
process.exit(falhou ? 1 : 0);
