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

const stub = createServer((req, res) => {
  res.setHeader('content-type', 'application/json');
  if (req.url?.endsWith('/models')) { res.end(JSON.stringify({ object: 'list', data: [{ id: 'modelo-quebrado', object: 'model' }] })); return; }
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
  // Conecta a API quebrada com a sessão da própria página (token só em memória: renova pelo cookie).
  const conexao = await page.evaluate(async (url) => {
    const cab = { 'content-type': 'application/json', 'X-Sora-Cliente': 'web' };
    const renovado = await (await fetch('/v1/auth/renovar', { method: 'POST', credentials: 'include', headers: cab })).json();
    const token = renovado.token_acesso ?? renovado.access_token ?? renovado.acesso;
    const r = await fetch('/v1/provedores', { method: 'POST', credentials: 'include', headers: { ...cab, authorization: `Bearer ${token}` }, body: JSON.stringify({ tipo: 'compativel_openai', chave: 'qa-chave', base_url: url }) });
    return { status: r.status, corpo: await r.text() };
  }, `http://127.0.0.1:${porta}/v1`);
  assert.equal(conexao.status, 201, `conectar provedor de teste: ${conexao.status} ${conexao.corpo}`);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await campo.waitFor({ state: 'visible', timeout: 15_000 });
  await campo.fill('crie uma campanha para minha cafeteria');
  await page.getByRole('button', { name: 'Enviar mensagem', exact: true }).click();
  await page.waitForURL(/\/projeto\//, { timeout: 30_000 });
  await page.getByText(/Não consegui falar com o seu modelo de IA/i).first().waitFor({ state: 'visible', timeout: 30_000 });
  assert.ok(await page.getByText('crie uma campanha para minha cafeteria').count() >= 1, 'o texto do usuário não se perde');
  assert.equal(await page.getByText(/^Plano ·/).count(), 0, 'erro do provedor não monta plano');
  await page.screenshot({ path: join(shots, 'e2e-10-erro-provedor-1440x900.png') });
  assert.deepEqual(erros, []);
} catch (e) { falha = e; } finally { await contexto.close(); await browser.close(); stub.close(); }
if (falha) { console.error(`FALHA erro do provedor: ${falha.stack ?? falha.message}`); process.exitCode = 1; }
else console.log('Erro do provedor aprovado: 201, aviso da Sora em PT-BR e mensagem do usuário preservada.');
