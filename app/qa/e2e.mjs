// Etapa 5: casca Sora · Bots · Grupos contra API, Postgres, Redis e SSE reais.
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const BASE = process.env.SORA_QA_BASE ?? 'http://localhost:5383';
// `entrar.mjs` atende vários QAs antigos e ainda tem 5173 como padrão. Importe-o
// depois de fixar a origem desta etapa para login, API e página usarem a mesma porta.
process.env.SORA_QA_BASE ??= BASE;
const { entrarNoContexto } = await import('./entrar.mjs');
const qaDir = dirname(fileURLToPath(import.meta.url));
const shots = join(qaDir, 'shots');
const erros = [];
const streams429 = [];

await mkdir(shots, { recursive: true });
const browser = await chromium.launch({ headless: true });
const contexto = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' });
const sessao = await entrarNoContexto(contexto, { email: process.env.SORA_QA_E2E_EMAIL ?? 'qa-e2e@sora.local', limparConversas: true });
const auth = { Authorization: `Bearer ${sessao.token_acesso}` };
// A conta de QA não acumula grupos de rodadas anteriores (o login limpa só conversas e bots).
for (const grupo of await (await contexto.request.get(`${BASE}/v1/grupos`, { headers: auth })).json()) {
  await contexto.request.post(`${BASE}/v1/canais-equipe/${grupo.id}/arquivar`, { headers: auth, failOnStatusCode: false });
}
// Propostas de grupo abertas de rodadas anteriores também não podem poluir o chat da Sora.
for (const proposta of await (await contexto.request.get(`${BASE}/v1/grupos/propostas`, { headers: auth })).json()) {
  await contexto.request.post(`${BASE}/v1/grupos/propostas/${proposta.id}/recusar`, { headers: auth, failOnStatusCode: false });
}
const page = await contexto.newPage();
page.on('console', mensagem => { if (mensagem.type() === 'error') erros.push({ tipo: 'console', texto: mensagem.text(), url: page.url() }); });
page.on('pageerror', erro => erros.push({ tipo: 'pageerror', texto: erro.message, url: page.url() }));
page.on('response', resposta => { if (resposta.status() === 429 && resposta.url().includes('/eventos')) streams429.push(resposta.url()); });
page.on('response', resposta => { if (process.env.SORA_QA_DEBUG && resposta.status() >= 400) console.log('[http]', resposta.status(), resposta.request().method(), resposta.url()); });

const foto = nome => page.screenshot({ path: join(shots, `e2e-etapa5-${nome}.png`), fullPage: false });
const post = async (caminho, data) => {
  const resposta = await contexto.request.post(`${BASE}${caminho}`, { headers: auth, data, failOnStatusCode: false });
  const corpo = resposta.status() === 204 ? null : await resposta.json().catch(() => null);
  assert.ok(resposta.ok(), `${caminho} falhou (${resposta.status()}): ${JSON.stringify(corpo)}`);
  return corpo;
};

let falha;
try {
  const resposta = await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 30_000 });
  assert.ok(resposta?.ok(), 'a conversa da Sora deve responder 2xx');
  await page.getByRole('textbox', { name: 'Mensagem para a Sora…' }).waitFor({ state: 'visible', timeout: 20_000 });
  await page.getByRole('link', { name: 'Conversar com a Sora' }).waitFor({ state: 'visible' });
  await page.getByRole('link', { name: 'Bots', exact: true }).waitFor({ state: 'visible' });
  await page.getByRole('link', { name: 'Grupos', exact: true }).waitFor({ state: 'visible' });
  const buscar = page.getByRole('button', { name: 'Buscar', exact: false });
  await buscar.waitFor({ state: 'visible' });
  await page.getByRole('link', { name: 'Configurações', exact: true }).waitFor({ state: 'visible' });
  assert.equal(await page.getByText('Projetos', { exact: true }).count(), 0);
  assert.equal(await page.getByText('Plugins', { exact: true }).count(), 0);
  assert.equal(await page.getByText(/Aprovar e publicar/i).count(), 0);
  assert.equal(await page.getByRole('button', { name: /microfone/i }).count(), 0, 'microfone não aparece na Sora');
  await buscar.click();
  const paleta = page.getByRole('dialog', { name: 'Paleta de comandos' });
  await paleta.getByText('Conversar com a Sora', { exact: true }).waitFor({ state: 'visible' });
  assert.equal(await paleta.getByText(/Projeto|Plugin|Ilha|Criar agente/i).count(), 0, 'Ctrl+K não expõe entradas antigas');
  await page.keyboard.press('Escape');
  await foto('01-sora');

  for (const caminho of ['/projetos', '/projeto/legado', '/revisao/legado', '/chat/sora']) {
    await page.goto(`${BASE}${caminho}`, { waitUntil: 'domcontentloaded' });
    await page.waitForURL(`${BASE}/`);
  }
  await page.goto(`${BASE}/agentes`, { waitUntil: 'domcontentloaded' });
  await page.waitForURL(`${BASE}/bots`);
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });

  // O endpoint real persiste o rascunho e publica bot.rascunho no SSE; só o clique no cartão cria o bot.
  const nomes = [`Bot QA ${Date.now()}`, `Bot QA ${Date.now() + 1}`];
  const nomeGrupo = `Grupo QA ${Date.now()}`;
  for (const [indice, nome] of nomes.entries()) {
    await post('/v1/bots/rascunhos', { descricao: `${nome}: organize informações com objetividade` });
    const cartao = page.getByRole('article', { name: /Rascunho do bot/i }).last();
    await cartao.waitFor({ state: 'visible', timeout: 20_000 });
    if (indice === 0) {
      // Com a listagem de pendentes no ar (GET /v1/bots/rascunhos), o cartão sobrevive à recarga.
      const pendentes = await contexto.request.get(`${BASE}/v1/bots/rascunhos`, { headers: auth, failOnStatusCode: false });
      if (pendentes.status() === 200) {
        await page.reload({ waitUntil: 'domcontentloaded' });
        await cartao.waitFor({ state: 'visible', timeout: 20_000 });
      } else console.log(`(aviso) GET /v1/bots/rascunhos respondeu ${pendentes.status()}: recarga do cartão não conferida`);
    }
    await cartao.getByLabel('Nome').fill(nome);
    await cartao.getByRole('button', { name: 'Criar bot' }).click();
    await page.getByText('Bot criado', { exact: true }).last().waitFor({ state: 'visible', timeout: 20_000 });
    await page.getByRole('link', { name: `Abrir conversa com ${nome}` }).waitFor({ state: 'visible', timeout: 20_000 });
    await page.locator('aside.sidebar').getByText(nome, { exact: true }).waitFor({ state: 'visible', timeout: 20_000 });
    if (indice === 0) await foto('02-rascunho-bot');
  }

  const agentes = await contexto.request.get(`${BASE}/v1/agentes`, { headers: auth });
  assert.equal(agentes.status(), 200);
  const bots = (await agentes.json()).filter(agente => nomes.includes(agente.nome));
  assert.equal(bots.length, 2, 'os dois bots confirmados devem existir');

  await page.locator('aside.sidebar').getByText(nomes[0], { exact: true }).click();
  await page.waitForURL(new RegExp(`/bots/${bots.find(bot => bot.nome === nomes[0]).id}$`));
  await page.getByRole('button', { name: 'Ativar microfone' }).waitFor({ state: 'visible' });
  await page.getByRole('tab', { name: 'Trabalho' }).waitFor({ state: 'visible' });
  await page.getByRole('tab', { name: 'Recursos' }).click();
  await page.getByText('Rotinas', { exact: true }).waitFor({ state: 'visible' });
  await page.getByText('Memória', { exact: true }).waitFor({ state: 'visible' });
  await page.getByText('Ferramentas', { exact: true }).waitFor({ state: 'visible' });
  await foto('03-bot-recursos');

  await page.goto(`${BASE}/chat/${bots.find(bot => bot.nome === nomes[0]).id}`, { waitUntil: 'domcontentloaded' });
  await page.waitForURL(new RegExp(`/bots/${bots.find(bot => bot.nome === nomes[0]).id}$`));
  await page.goto(`${BASE}/canais/legado`, { waitUntil: 'domcontentloaded' });
  await page.waitForURL(`${BASE}/grupos`);

  await page.getByRole('button', { name: 'Criar grupo' }).click();
  const modal = page.getByRole('dialog', { name: 'Reúna seus bots' });
  await modal.getByLabel('Nome do grupo').fill(nomeGrupo);
  for (const nome of nomes) await modal.getByText(nome, { exact: true }).click();
  await modal.getByRole('button', { name: 'Criar grupo', exact: true }).click();
  await page.waitForURL(/\/grupos\/[0-9a-f-]+$/i, { timeout: 20_000 });
  await page.getByText(nomeGrupo, { exact: true }).first().waitFor({ state: 'visible' });
  await page.getByText('Sora', { exact: true }).first().waitFor({ state: 'visible' });
  // A Sora lidera o grupo mas não conta como bot na barra lateral.
  await page.locator('aside.sidebar').getByRole('link', { name: new RegExp(nomeGrupo) }).getByText(/^(2 bots|Trabalhando|Precisa de você)$/).waitFor({ state: 'visible', timeout: 10_000 });
  await foto('04-grupo');

  const urlGrupo = page.url();
  for (let i = 0; i < 5; i += 1) {
    await page.reload({ waitUntil: 'domcontentloaded' });
    // Espera o app pronto (sessão renovada) antes da próxima recarga, como um usuário faria.
    await page.getByText(nomeGrupo, { exact: true }).first().waitFor({ state: 'visible', timeout: 20_000 });
    assert.equal(page.url(), urlGrupo, 'a rota do grupo deve sobreviver à recarga');
  }
  assert.deepEqual(streams429, [], `recargas não podem esgotar streams SSE:\n${streams429.join('\n')}`);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(300);
  const largura = await page.evaluate(() => ({ pagina: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth }));
  assert.ok(largura.pagina <= largura.viewport, `a interface não pode rolar na horizontal (${largura.pagina}/${largura.viewport})`);
  // Título da topbar não pode ficar por cima da marca (orb) no celular.
  const sobreposicao = await page.evaluate(() => {
    const marca = document.querySelector('.topbar-title .mobile-brand')?.getBoundingClientRect();
    const titulo = document.querySelector('.topbar-title strong')?.getBoundingClientRect();
    return marca && titulo ? marca.right - titulo.left : null;
  });
  assert.ok(sobreposicao !== null && sobreposicao <= 0, `título da topbar sobre a marca no celular (${sobreposicao}px)`);
  await foto('05-grupo-390');
  assert.deepEqual(erros, [], `console deve ficar limpo:\n${JSON.stringify(erros, null, 2)}`);
} catch (erro) {
  falha = erro;
  await foto('FALHA').catch(() => undefined);
} finally {
  await writeFile(join(shots, 'e2e-console.json'), `${JSON.stringify(erros, null, 2)}\n`, 'utf8');
  await contexto.close();
  await browser.close();
}

if (falha || erros.length) {
  if (falha) console.error(`FALHA E2E etapa 5: ${falha.stack ?? falha.message}`);
  process.exitCode = 1;
} else console.log('E2E etapa 5 aprovado: Sora, rascunhos reais, bots, grupo, redirecionamentos, SSE e layout móvel; console limpo.');
