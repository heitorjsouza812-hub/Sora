// Lince — rodada 2: valida o Tauri real via CDP sem imprimir tokens.
// Uso: node qa/lince-tauri-r2.mjs <entrar|estado|ilha|sair>
import { chromium } from '@playwright/test';

const ACAO = process.argv[2] ?? 'estado';
const BASE_CDP = 'http://127.0.0.1:9333';
const EMAIL = 'qa@sora.local';
const SENHA = 'sora-qa-senha-123';

const browser = await chromium.connectOverCDP(BASE_CDP);
const paginas = browser.contexts().flatMap((contexto) => contexto.pages());
const main = paginas.find((pagina) => !pagina.url().includes('janela=ilha'));
const ilha = paginas.find((pagina) => pagina.url().includes('janela=ilha'));
if (!main || !ilha) throw new Error(`Esperava main + ilha; encontrei: ${paginas.map((p) => p.url()).join(', ')}`);

const respostas = [];
const consoleErros = [];
for (const [nome, pagina] of [['main', main], ['ilha', ilha]]) {
  pagina.on('response', (resposta) => {
    if (resposta.url().includes('/v1/auth/')) respostas.push(`${nome} ${resposta.status()} ${resposta.request().method()} ${new URL(resposta.url()).pathname}`);
  });
  pagina.on('console', (mensagem) => {
    if (mensagem.type() === 'error') consoleErros.push(`${nome} console: ${mensagem.text()}`);
  });
  pagina.on('pageerror', (erro) => consoleErros.push(`${nome} pageerror: ${erro.message}`));
}

const h1 = async () => main.locator('h1').first().innerText().catch(() => '(sem h1)');
const armazenamento = async (pagina) => pagina.evaluate(() => {
  const local = Object.fromEntries(Array.from({ length: localStorage.length }, (_, i) => {
    const chave = localStorage.key(i);
    return [chave, localStorage.getItem(chave)];
  }));
  const sessao = Object.fromEntries(Array.from({ length: sessionStorage.length }, (_, i) => {
    const chave = sessionStorage.key(i);
    return [chave, sessionStorage.getItem(chave)];
  }));
  const bruto = JSON.stringify({ local, sessao, cookie: document.cookie });
  return {
    localKeys: Object.keys(local),
    sessionKeys: Object.keys(sessao),
    cookieLegivel: document.cookie,
    contemTokenNomeado: /token[_-]?(acesso|renovacao|refresh)|sora_renovacao/i.test(bruto),
    contemJwt: /eyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{8,}/.test(bruto),
    contemSenhaQa: bruto.includes('sora-qa-senha-123'),
  };
});

async function recarregarEEsperar(pagina) {
  await pagina.reload({ waitUntil: 'domcontentloaded' });
  await pagina.waitForTimeout(1800);
}

console.log('targets:', JSON.stringify({ main: main.url(), ilha: ilha.url() }));
console.log('tauri:', JSON.stringify({
  main: await main.evaluate(() => Boolean(window.__TAURI_INTERNALS__)),
  ilha: await ilha.evaluate(() => Boolean(window.__TAURI_INTERNALS__)),
}));

if (ACAO === 'entrar') {
  await main.waitForLoadState('domcontentloaded');
  if (/Entrar na Sora/.test(await h1())) {
    await main.getByLabel('E-mail').fill(EMAIL);
    await main.getByLabel('Senha').fill(SENHA);
    await main.getByRole('button', { name: 'Entrar', exact: true }).click();
    await main.waitForFunction(() => !document.body.innerText.includes('Entrar na Sora'), null, { timeout: 15000 });
    await main.waitForTimeout(1200);
  }
  console.log('estado:', JSON.stringify({ h1: await h1(), url: main.url() }));
  console.log('storage-main:', JSON.stringify(await armazenamento(main)));
  console.log('auth:', JSON.stringify(respostas));
  await main.screenshot({ path: 'qa/shots/lince/tauri-r2-entrou.png' });
}

if (ACAO === 'estado') {
  await recarregarEEsperar(main);
  console.log('estado:', JSON.stringify({ h1: await h1(), url: main.url(), logado: !/Entrar na Sora/.test(await h1()) }));
  console.log('storage-main:', JSON.stringify(await armazenamento(main)));
  console.log('auth:', JSON.stringify(respostas));
  await main.screenshot({ path: 'qa/shots/lince/tauri-r2-reabriu.png' });
}

if (ACAO === 'ilha') {
  await recarregarEEsperar(main);
  await recarregarEEsperar(ilha);
  async function invocar(comando, argumentos = {}) {
    return ilha.evaluate(async ({ comando, argumentos }) => {
      try {
        const valor = await window.__TAURI_INTERNALS__.invoke(comando, argumentos);
        return { ok: true, devolveuValor: valor !== null && valor !== undefined };
      } catch (erro) {
        return { ok: false, erro: String(erro).slice(0, 400) };
      }
    }, { comando, argumentos });
  }
  // Se a capability estiver errada, token vazio ainda é rejeitado pelo Rust antes de gravar.
  const permissoes = {
    ler: await invocar('cofre_ler'),
    gravar: await invocar('cofre_gravar', { token: '' }),
    apagar: await invocar('cofre_apagar'),
  };
  console.log('cofre-na-ilha:', JSON.stringify(permissoes));
  console.log('storage-ilha:', JSON.stringify(await armazenamento(ilha)));
  console.log('console-erros:', JSON.stringify(consoleErros));
  console.log('csp-erros:', JSON.stringify(consoleErros.filter((erro) => /content security policy|refused to|csp/i.test(erro))));
}

if (ACAO === 'sair') {
  if (/Entrar na Sora/.test(await h1())) throw new Error('A janela principal já estava deslogada antes do teste de Sair.');
  const menuConta = main.getByRole('button', { name: 'Abrir menu da conta' });
  if (!(await menuConta.isVisible().catch(() => false))) {
    const pular = main.getByRole('button', { name: /Fazer isso depois/ });
    if (await pular.isVisible().catch(() => false)) await pular.click();
    await main.waitForTimeout(900);
  }
  await menuConta.click();
  await main.getByRole('menuitem', { name: 'Sair' }).click();
  await main.getByRole('heading', { name: /Entrar na Sora/ }).waitFor({ timeout: 10000 });
  await main.waitForTimeout(600);
  console.log('estado:', JSON.stringify({ h1: await h1(), url: main.url(), deslogado: true }));
  console.log('storage-main:', JSON.stringify(await armazenamento(main)));
  console.log('auth:', JSON.stringify(respostas));
  await main.screenshot({ path: 'qa/shots/lince/tauri-r2-saiu.png' });
}

if (!['entrar', 'estado', 'ilha', 'sair'].includes(ACAO)) throw new Error(`Ação desconhecida: ${ACAO}`);
await browser.close();
