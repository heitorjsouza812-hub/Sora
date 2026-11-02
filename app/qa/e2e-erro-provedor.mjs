// Erro do provedor: a API de modelos do usuário responde 500 no chat. A triagem falha, o POST volta 201
// e a Sora avisa em PT-BR no próprio chat (a mensagem do usuário não se perde).
// Precisa de uma API SEM modelo falso (SORA_MODELO_FALSO=0, PERMITIR_PROVEDOR_REDE_LOCAL=1) atrás do
// front em SORA_QA_BASE. Chamado por qa/e2e.mjs quando SORA_QA_BASE_ERRO está definido.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { entrarNoContexto, BASE } from './entrar.mjs';

const shots = join(dirname(fileURLToPath(import.meta.url)), 'shots');

// Modelo fora do catálogo: entra sem capacidades e o seletor o recusaria ANTES de chamar o provedor (o teste
// passaria sem falar com ele). O teste marca as capacidades pelo PATCH /v1/modelos/{id} e o stub conta as
// chamadas de chat: exige >= 1.
const chamadasDeChat = [];
const stub = createServer((req, res) => {
  res.setHeader('content-type', 'application/json');
  if (req.method === 'GET' && req.url?.endsWith('/models')) { res.end(JSON.stringify({ object: 'list', data: [{ id: 'modelo-local', object: 'model' }] })); return; }
  if (req.method === 'POST') chamadasDeChat.push(req.url);
  res.statusCode = 500; res.end(JSON.stringify({ error: { message: 'provedor fora do ar' } }));
});
await new Promise(r => stub.listen(0, '127.0.0.1', r));
const porta = stub.address().port;

const browser = await chromium.launch({ headless: true });
const contexto = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' });
const erros = [];
let falha;
try {
  await entrarNoContexto(contexto);
  const page = await contexto.newPage();
  page.on('pageerror', e => erros.push(e.message));
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  const campo = page.getByRole('textbox', { name: /Peça qualquer coisa à Sora/i });
  await campo.waitFor({ state: 'visible', timeout: 15_000 });
  // Conecta o provedor quebrado pela própria tela (cartão Compatível com OpenAI, URL editável)
  // e marca as capacidades do modelo fora do catálogo na tela Configurações > Modelos de IA.
  await page.goto(BASE + '/configuracoes', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: /Compatível com OpenAI/ }).click();
  await page.getByLabel('URL base').fill(`http://127.0.0.1:${porta}/v1`);
  await page.getByLabel('Chave da API').fill('qa-chave-local');
  await page.getByRole('button', { name: 'Testar e conectar', exact: true }).click();
  const capacidades = page.locator('.cfg-capacidades');
  await capacidades.waitFor({ state: 'visible', timeout: 30_000 });
  await capacidades.getByText('Modelo fora do catálogo').waitFor({ state: 'visible' });
  // o checkbox só muda depois do PATCH /v1/modelos/{id} (estado vem do servidor): clica e espera
  await capacidades.getByLabel('Ferramentas').click();
  await page.waitForFunction(() => document.querySelectorAll('.cfg-capacidades input:checked').length === 1, null, { timeout: 15_000 });
  await page.waitForFunction(() => !document.querySelector('.cfg-capacidades[disabled]'), null, { timeout: 15_000 });
  await capacidades.getByLabel('JSON').click();
  await page.waitForFunction(() => document.querySelectorAll('.cfg-capacidades input:checked').length >= 2, null, { timeout: 15_000 });
  assert.ok(await capacidades.getByLabel('Ferramentas').isChecked(), 'as capacidades marcadas precisam continuar na tela');
  await page.screenshot({ path: join(shots, 'e2e-14-capacidades-1440x900.png') });
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await campo.waitFor({ state: 'visible', timeout: 15_000 });
  await campo.fill('crie uma campanha para minha cafeteria');
  await page.getByRole('button', { name: 'Enviar mensagem', exact: true }).click();
  await page.waitForURL(/\/projeto\//, { timeout: 30_000 });
  await page.getByText(/Não consegui falar com o seu modelo de IA/i).first().waitFor({ state: 'visible', timeout: 30_000 });
  assert.ok(await page.getByText('crie uma campanha para minha cafeteria').count() >= 1, 'o texto do usuário não se perde');
  assert.equal(await page.getByText(/^Plano ·/).count(), 0, 'erro do provedor não monta plano');
  assert.ok(chamadasDeChat.length >= 1, 'o backend precisa ter chamado o provedor HTTP (POST de chat), e não ter recusado antes');
  // C1: depois do aviso, o "pensando" não pode ficar para sempre
  await page.waitForFunction(() => !/pensando/i.test(document.querySelector('.chat-header, header')?.textContent ?? '') && !document.querySelector('.thinking-row'), null, { timeout: 15_000 });
  await page.screenshot({ path: join(shots, 'e2e-10-erro-provedor-1440x900.png') });
  assert.deepEqual(erros, []);
} catch (e) { falha = e; try { await contexto.pages()[0]?.screenshot({ path: join(shots, 'e2e-erro-provedor-FALHA.png') }); } catch { /* página encerrada */ } } finally { await contexto.close(); await browser.close(); stub.close(); }
if (falha) { console.error(`FALHA erro do provedor: ${falha.stack ?? falha.message}`); process.exitCode = 1; }
else console.log(`Erro do provedor aprovado: o provedor HTTP local recebeu ${chamadasDeChat.length} chamada(s) e falhou; 201, aviso da Sora em PT-BR, mensagem preservada e sem "pensando".`);
