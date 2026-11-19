// Fotos do README (docs/imagens/): conta de demonstração, bots e grupo de exemplo, modelo falso.
//
// Precisa do backend com SORA_MODELO_FALSO=1, do worker, do Vite (5173) e de um provedor
// "compatível com OpenAI" que liste modelos (qualquer servidor que responda GET /v1/models).
// Nunca use uma conta de verdade: o roteiro cria a dele com o convite de SORA_README_CONVITE.
//
//   SORA_README_CONVITE=… SORA_README_MODELOS=http://127.0.0.1:18080/v1 node qa/readme-fotos.mjs
import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const BASE = process.env.SORA_QA_BASE ?? 'http://localhost:5173';
const CONVITE = process.env.SORA_README_CONVITE;
const MODELOS = process.env.SORA_README_MODELOS ?? 'http://127.0.0.1:18080/v1';
const SAIDA = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'docs', 'imagens');
const EMAIL = 'ana@exemplo.com';
const SENHA = 'senha-de-demonstracao-123';

if (!CONVITE) throw new Error('Defina SORA_README_CONVITE (convite de uso único criado pelo CLI do backend).');

async function api(request, metodo, caminho, dados, token) {
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const resp = await request.fetch(`${BASE}${caminho}`, { method: metodo, data: dados, headers, failOnStatusCode: false });
  let corpo = null;
  try { corpo = await resp.json(); } catch { /* sem corpo */ }
  if (resp.status() >= 400) throw new Error(`${metodo} ${caminho} → ${resp.status()} ${JSON.stringify(corpo)}`);
  return corpo;
}

async function preparar(contexto) {
  const { request } = contexto;
  const existe = await request.post(`${BASE}/v1/auth/entrar`, { data: { email: EMAIL, senha: SENHA }, failOnStatusCode: false });
  if (existe.status() === 200) {
    // rodada anterior já criou a conta de demonstração: reaproveita bots e grupo
    const { token_acesso: token } = await existe.json();
    const ids = (await api(request, 'GET', '/v1/agentes', undefined, token)).filter(a => a.tipo !== 'sora').map(a => a.id);
    const grupos = await api(request, 'GET', '/v1/grupos', undefined, token);
    await contexto.addInitScript(() => { try { localStorage.setItem('sora.sessao.marca.v1', '1'); } catch { /* */ } });
    return { token, ids, grupoId: grupos[0]?.id };
  }
  await api(request, 'POST', '/v1/auth/cadastrar', { nome: 'Ana Souza', email: EMAIL, senha: SENHA, convite: CONVITE });
  const { token_acesso: token } = await api(request, 'POST', '/v1/auth/entrar', { email: EMAIL, senha: SENHA });
  await api(request, 'POST', '/v1/provedores', { tipo: 'compativel_openai', chave: 'demo', base_url: MODELOS }, token);
  const bots = [];
  for (const descricao of [
    'Um bot que pesquisa os concorrentes da minha cafeteria e resume preços e novidades toda semana',
    'Um bot que escreve posts para o Instagram da cafeteria com um tom leve e divertido',
    'Um bot que todo dia de manhã me traz as notícias de café e de pequenos negócios',
  ]) {
    bots.push(await api(request, 'POST', '/v1/bots/criar-por-descricao', { descricao }, token));
  }
  const ids = bots.map(b => b.id ?? b.agente_id ?? b.bot?.id).filter(Boolean);
  const grupo = await api(request, 'POST', '/v1/grupos', {
    nome: 'Lançamento da cafeteria', membros: ids.slice(0, 3),
    proposito: 'Planejar o lançamento: pesquisa, posts e calendário.',
  }, token);
  await contexto.addInitScript(() => { try { localStorage.setItem('sora.sessao.marca.v1', '1'); } catch { /* */ } });
  return { token, ids, grupoId: grupo.id ?? grupo.grupo_id ?? grupo.canal_id };
}

async function foto(pagina, nome, espera = 2_500) {
  await pagina.waitForTimeout(espera); // o mascote termina de "chegar" e a página assenta
  await pagina.screenshot({ path: join(SAIDA, `${nome}.png`) });
  console.log('foto', nome);
}

const navegador = await chromium.launch();
await mkdir(SAIDA, { recursive: true });
try {
  const contexto = await navegador.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark', locale: 'pt-BR' });
  const { token, ids, grupoId } = await preparar(contexto);
  const pagina = await contexto.newPage();

  await pagina.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
  await foto(pagina, 'inicio', 3_500);

  await pagina.goto(`${BASE}/bots/novo`, { waitUntil: 'domcontentloaded' });
  await foto(pagina, 'novo-bot');

  // cartão de rascunho: o que a Sora mostra quando alguém pede um bot (montado por regras aqui)
  await pagina.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
  await pagina.waitForTimeout(1_500);
  await api(contexto.request, 'POST', '/v1/bots/rascunhos', {
    descricao: 'Um bot que acompanha o preço do café em três fornecedores e me avisa quando baixar',
  }, token);
  await pagina.getByRole('article', { name: /Rascunho do bot/i }).last().waitFor({ state: 'visible', timeout: 20_000 });
  await foto(pagina, 'rascunho-de-bot');

  await pagina.goto(`${BASE}/bots/${ids[1] ?? ids[0]}`, { waitUntil: 'domcontentloaded' });
  await pagina.getByRole('tab', { name: 'Recursos' }).click();
  await foto(pagina, 'bot-recursos');

  if (grupoId) {
    await pagina.goto(`${BASE}/grupos/${grupoId}`, { waitUntil: 'domcontentloaded' });
    await foto(pagina, 'grupo');
  }

  await pagina.goto(`${BASE}/configuracoes`, { waitUntil: 'domcontentloaded' });
  await foto(pagina, 'configuracoes');

  const celular = await navegador.newContext({
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, colorScheme: 'dark', locale: 'pt-BR',
    storageState: await contexto.storageState(),
  });
  await celular.addInitScript(() => { try { localStorage.setItem('sora.sessao.marca.v1', '1'); } catch { /* */ } });
  const telefone = await celular.newPage();
  await telefone.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
  await foto(telefone, 'celular', 3_500);
} finally {
  await navegador.close();
}
