// Login de QA (etapa 2, regra 7): entra com uma conta de teste antes dos fluxos.
// Credenciais por env: SORA_QA_EMAIL / SORA_QA_SENHA (padrão: qa@sora.local / sora-qa-senha-123).
// Se a conta não existir, cria com convite: SORA_QA_CONVITE, ou um convite novo gerado pelo CLI do
// backend (`uv run python -m app.cli convite criar`, em ../backend). Precisa do backend local rodando
// e do dev server do Vite (proxy /v1 → :8000).
//
// Uso:
//   import { entrarNoContexto } from './entrar.mjs';
//   const contexto = await browser.newContext(...);
//   await entrarNoContexto(contexto);            // cookie de renovação no contexto + pula o onboarding
//   const page = await contexto.newPage();       // a página abre já logada (renovação silenciosa)
//
// Rodar sozinho (cria/valida a conta): node qa/entrar.mjs
import { execFileSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const BASE = process.env.SORA_QA_BASE ?? 'http://localhost:5173';
export const QA_EMAIL = process.env.SORA_QA_EMAIL ?? 'qa@sora.local';
export const QA_SENHA = process.env.SORA_QA_SENHA ?? 'sora-qa-senha-123';
const QA_NOME = process.env.SORA_QA_NOME ?? 'Conta de QA';
const backendDir = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'backend');

function conviteDoCli() {
  if (process.env.SORA_QA_CONVITE) return process.env.SORA_QA_CONVITE;
  const codigo = `QA-${Date.now().toString(36).toUpperCase()}`;
  const env = { ...process.env, AMBIENTE: process.env.AMBIENTE ?? 'desenvolvimento' };
  try {
    execFileSync('uv', ['run', 'python', '-m', 'app.cli', 'convite', 'criar', '--codigo', codigo, '--usos', '1'],
      { cwd: backendDir, env, stdio: ['ignore', 'pipe', 'pipe'], shell: process.platform === 'win32' });
  } catch (erro) {
    throw new Error(`Não consegui criar o convite de QA pelo CLI do backend (defina SORA_QA_CONVITE): ${erro.stderr?.toString() || erro.message}`);
  }
  return codigo;
}

async function postar(request, caminho, dados) {
  const resp = await request.post(`${BASE}${caminho}`, { data: dados, failOnStatusCode: false });
  let corpo = null;
  try { corpo = await resp.json(); } catch { /* 201/204 sem corpo */ }
  return { status: resp.status(), corpo };
}

/** Entra (criando a conta de QA se faltar) usando o `request` do contexto, que divide os cookies com as páginas. */
export async function entrarNoContexto(contexto, { pularOnboarding = true } = {}) {
  const { request } = contexto;
  let r = await postar(request, '/v1/auth/entrar', { email: QA_EMAIL, senha: QA_SENHA });
  if (r.status === 401) {
    const c = await postar(request, '/v1/auth/cadastrar', { nome: QA_NOME, email: QA_EMAIL, senha: QA_SENHA, convite: conviteDoCli() });
    if (c.status !== 201) throw new Error(`Cadastro da conta de QA falhou (${c.status}): ${JSON.stringify(c.corpo)}`);
    r = await postar(request, '/v1/auth/entrar', { email: QA_EMAIL, senha: QA_SENHA });
  }
  if (r.status !== 200) {
    const dica = r.status >= 500 || r.status === 404 ? ' O backend está rodando na porta 8000?' : '';
    throw new Error(`Login de QA falhou (${r.status}): ${JSON.stringify(r.corpo)}.${dica}`);
  }
  // Os fluxos de QA não conectam provedor: o onboarding fica "para depois" (o aviso aparece na Home).
  if (pularOnboarding) {
    await contexto.addInitScript(() => { try { sessionStorage.setItem('sora.onboarding-pulado.v1', '1'); } catch { /* */ } });
  }
  return r.corpo;
}

/** Entra pela tela (para testar a própria tela Entrar). */
export async function entrarPelaTela(page) {
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.getByLabel('E-mail').fill(QA_EMAIL);
  await page.getByLabel('Senha').fill(QA_SENHA);
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const { chromium } = await import('@playwright/test');
  const browser = await chromium.launch({ headless: true });
  try {
    const contexto = await browser.newContext();
    await entrarNoContexto(contexto);
    const eu = await contexto.request.post(`${BASE}/v1/auth/renovar`);
    console.log(`Conta de QA ok: ${QA_EMAIL} (renovação pelo cookie: ${eu.status()})`);
  } finally {
    await browser.close();
  }
}

/** Faz todo `browser.newContext()` já sair logado (usado pelos scripts de QA). */
export function logarTodoContexto(browser, opcoes) {
  const novoContexto = browser.newContext.bind(browser);
  browser.newContext = async (...args) => {
    const contexto = await novoContexto(...args);
    await entrarNoContexto(contexto, opcoes);
    return contexto;
  };
  return browser;
}
