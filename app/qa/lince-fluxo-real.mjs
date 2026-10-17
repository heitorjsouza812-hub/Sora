// Lince — fluxo real da etapa 2 (conta nova → onboarding → provedor falso → Configurações → Sair/Entrar).
// Uso: node qa/lince-fluxo-real.mjs [1440|390]   (precisa do backend :8000, vite :5173 e do qa/lince-provedor-falso.mjs :8765)
import { readFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const BASE = 'http://localhost:5173';
const qa = dirname(fileURLToPath(import.meta.url));
const W = Number(process.argv[2] ?? 1440);
const H = W < 600 ? 844 : 900;
const shots = join(qa, 'shots', 'lince', String(W));
mkdirSync(shots, { recursive: true });
const CHAVE = /CHAVE_VALIDA = '([^']+)'/.exec(readFileSync(join(qa, 'lince-provedor-falso.mjs'), 'utf8'))[1];
const ERRADA = 'sk-lince-errada-000000';
const email = `lince${Date.now()}@sora.local`;
const senha = 'lince-senha-forte-123';
const CONVITE = process.env.LINCE_CONVITE ?? 'QA-TECELA';

const resultados = [];
const ok = (nome, cond, extra = '') => { resultados.push({ nome, ok: !!cond, extra }); console.log(`${cond ? 'PASS' : 'FAIL'}  ${nome}${extra ? '  — ' + extra : ''}`); };
const consoleErros = [];
const respostas = []; // {url, status, corpo}
const pedidos = [];   // {url, metodo, corpo}
let n = 0;

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: W, height: H } });
const page = await ctx.newPage();
page.on('console', m => { if (m.type() === 'error') consoleErros.push(m.text()); });
page.on('pageerror', e => consoleErros.push('pageerror: ' + e.message));
page.on('request', r => { if (r.url().includes('/v1/')) pedidos.push({ url: r.url(), metodo: r.method(), corpo: r.postData() ?? '' }); });
page.on('response', async r => { if (r.url().includes('/v1/')) { let corpo = ''; try { corpo = await r.text(); } catch {} respostas.push({ url: r.url(), status: r.status(), corpo, hdr: r.headers() }); } });
const snap = async (nome) => { n += 1; await page.screenshot({ path: join(shots, `${String(n).padStart(2, '0')}-${nome}.png`) }); };
const esperar = (ms) => page.waitForTimeout(ms);

async function sairPelaUI() {
  if (W < 600) {
    await page.getByRole('button', { name: 'Abrir menu', exact: true }).click();
    await esperar(400);
    const alcance = await page.getByRole('button', { name: 'Abrir menu da conta' }).isVisible().catch(() => false);
    const sairVisivel = await page.getByText('Sair', { exact: true }).first().isVisible().catch(() => false);
    ok('390px: dá para Sair / abrir Configurações pelo menu', alcance || sairVisivel, 'conta e ações disponíveis no BottomSheet');
    await snap('menu-mobile');
    if (!(alcance || sairVisivel)) {
      // contorno: encerra a sessão pela API para seguir o roteiro
      await page.evaluate(() => fetch('/v1/auth/sair', { method: 'POST', credentials: 'include' }));
      await page.reload({ waitUntil: 'domcontentloaded' });
      await page.getByRole('heading', { name: /Entrar na Sora/ }).waitFor({ timeout: 8000 });
      return;
    }
    if (sairVisivel) {
      await page.getByRole('button', { name: 'Sair', exact: true }).click();
      await page.getByRole('heading', { name: /Entrar na Sora/ }).waitFor({ timeout: 8000 });
      return;
    }
  }
  await page.getByRole('button', { name: 'Abrir menu da conta' }).click();
  await page.getByRole('menuitem', { name: 'Sair' }).click();
  await page.getByRole('heading', { name: /Entrar na Sora/ }).waitFor({ timeout: 8000 });
}

try {
  // 1. sem login → Entrar
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.getByRole('heading', { name: /Entrar na Sora/ }).waitFor({ timeout: 10000 });
  ok('sem sessão mostra tela Entrar', true);
  await snap('entrar');

  // 2. criar conta com convite ruim → erro PT-BR; depois convite certo
  await page.getByRole('tab', { name: 'Criar conta' }).click();
  await page.getByLabel('Nome').fill('Lince Teste');
  await page.getByLabel('E-mail').fill(email);
  await page.getByLabel('Senha').fill(senha);
  await page.getByLabel('Código de convite').fill('CONVITE-INEXISTENTE');
  await page.getByRole('button', { name: 'Criar conta', exact: true }).click();
  const alerta = page.getByRole('alert').first();
  await alerta.waitFor({ timeout: 8000 });
  ok('convite inválido mostra erro em PT-BR', /[a-zçãé]/i.test(await alerta.innerText()), await alerta.innerText());
  await snap('convite-invalido');
  await page.getByLabel('Código de convite').fill(CONVITE);
  await page.getByRole('button', { name: 'Criar conta', exact: true }).click();

  // 3. onboarding
  await page.getByRole('heading', { name: /conecte sua primeira API/i }).waitFor({ timeout: 15000 });
  ok('onboarding aparece (conta sem provedor)', true);
  await snap('onboarding');

  const cc = page.locator('article.cfg-provider-card').filter({ has: page.locator('strong', { hasText: /^Compatível com OpenAI$/ }) });
  const resumo = cc.locator('button.cfg-provider-summary');
  if ((await resumo.getAttribute('aria-expanded')) !== 'true') await resumo.click();
  await esperar(300);
  const url = cc.getByLabel('URL base');
  await url.fill('http://localhost:8765/v1');
  // chave errada → 422
  await cc.getByLabel('Chave da API').fill(ERRADA);
  await cc.getByRole('button', { name: 'Testar e conectar' }).click();
  const fb = cc.locator('.cfg-card-feedback');
  await page.waitForFunction(() => { const f = [...document.querySelectorAll('article.cfg-provider-card')].find(a => a.textContent.includes('Compatível com OpenAI'))?.querySelector('.cfg-card-feedback'); return f && f.textContent && !/Falando com o servidor/.test(f.textContent) && f.textContent.trim().length > 0; }, null, { timeout: 15000 });
  const msg422 = (await fb.innerText()).trim();
  const r422 = respostas.find(r => r.url.includes('/v1/provedores') && r.status >= 400);
  ok('chave errada → status 422 do backend', r422?.status === 422, `status=${r422?.status} corpo=${r422?.corpo?.slice(0, 200)}`);
  ok('chave errada → mensagem PT-BR na tela', /[ãçéíõ]|chave|inválid|rejeit|não/i.test(msg422) && !/Incorrect API key/i.test(msg422), msg422);
  await snap('chave-errada');

  // chave certa
  await cc.getByLabel('Chave da API').fill(CHAVE);
  await cc.getByRole('button', { name: 'Testar e conectar' }).click();
  await page.waitForFunction(() => !document.body.innerText.includes('conecte sua primeira API'), null, { timeout: 15000 }).catch(() => {});
  await esperar(800);
  const aindaOnb = await page.getByRole('heading', { name: /conecte sua primeira API/i }).isVisible().catch(() => false);
  ok('conectar com a chave certa sai do onboarding', !aindaOnb);
  await snap('pos-conexao');

  // 4. Configurações
  await page.goto(`${BASE}/configuracoes`, { waitUntil: 'domcontentloaded' });
  await page.getByRole('heading', { name: /Configura/ }).first().waitFor({ timeout: 10000 });
  await esperar(500);
  const card = page.locator('article.cfg-provider-card').filter({ has: page.locator('strong', { hasText: /^Compatível com OpenAI$/ }) });
  if ((await card.locator('button.cfg-provider-summary').getAttribute('aria-expanded')) !== 'true') await card.locator('button.cfg-provider-summary').click();
  await esperar(400);
  ok('cartão mostra Conectado', /Conectado/.test(await card.innerText()) && !/Não conectado/.test(await card.locator('.cfg-status').innerText()));
  const linhas = card.locator('.cfg-model-row');
  const nModelos = await linhas.count();
  const nomes = await card.locator('.cfg-model-name strong').allInnerTexts();
  ok('3 modelos do provedor falso aparecem', nModelos === 3 && ['lince-pequeno', 'lince-medio', 'lince-grande'].every(x => nomes.some(nm => nm.endsWith(x))), nomes.join(','));
  ok('final da chave mostrado (…' + CHAVE.slice(-4) + ')', (await card.innerText()).includes(CHAVE.slice(-4)));
  ok('chave inteira NÃO aparece no DOM', !(await page.content()).includes(CHAVE));
  await snap('config-conectado');

  // nível
  const linhaMedio = card.locator('.cfg-model-row', { hasText: 'lince-medio' });
  const nivelAntes = await linhaMedio.locator('select').inputValue();
  await linhaMedio.locator('select').selectOption('N3');
  await esperar(900);
  // ativo
  const linhaPeq = card.locator('.cfg-model-row', { hasText: 'lince-pequeno' });
  const ativoAntes = await linhaPeq.locator('input[type=checkbox]').isChecked();
  await linhaPeq.locator('.cfg-switch').click();
  await esperar(900);
  // teto
  const teto = card.getByLabel('Teto mensal (USD)');
  await teto.fill('7.5');
  await card.getByRole('button', { name: 'Salvar alterações' }).click();
  await esperar(900);
  // prioridade
  const prio = page.getByLabel('Priorizar');
  await prio.selectOption('qualidade');
  await esperar(900);
  await snap('config-alterado');

  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.getByRole('heading', { name: /Configura/ }).first().waitFor({ timeout: 10000 });
  await esperar(900);
  const card2 = page.locator('article.cfg-provider-card').filter({ has: page.locator('strong', { hasText: /^Compatível com OpenAI$/ }) });
  if ((await card2.locator('button.cfg-provider-summary').getAttribute('aria-expanded')) !== 'true') await card2.locator('button.cfg-provider-summary').click();
  await esperar(400);
  ok(`nível persistiu (${nivelAntes} → N3) após recarregar`, (await card2.locator('.cfg-model-row', { hasText: 'lince-medio' }).locator('select').inputValue()) === 'N3');
  ok(`ativo persistiu (${ativoAntes} → ${!ativoAntes})`, (await card2.locator('.cfg-model-row', { hasText: 'lince-pequeno' }).locator('input[type=checkbox]').isChecked()) === !ativoAntes);
  ok('teto 7,5 persistiu', (await card2.getByLabel('Teto mensal (USD)').inputValue()) === '7.50' || (await card2.getByLabel('Teto mensal (USD)').inputValue()) === '7.5', await card2.getByLabel('Teto mensal (USD)').inputValue());
  ok('prioridade qualidade persistiu', (await page.getByLabel('Priorizar').inputValue()) === 'qualidade');
  await snap('config-recarregado');

  // padrões só listam modelos ativos
  const opcoesSora = await page.locator('.cfg-defaults label').filter({ hasText: 'Sora' }).first().locator('option').allInnerTexts();
  ok('padrão da Sora lista só modelos ativos (sem lince-pequeno inativo)', !opcoesSora.some(o => o.includes('lince-pequeno')) && opcoesSora.some(o => o.includes('lince-medio')), 'opcoes=' + opcoesSora.join(' | '));

  // 5. desconectar
  await card2.getByRole('button', { name: 'Desconectar' }).click();
  await esperar(1200);
  const st = await card2.locator('.cfg-status').innerText();
  ok('desconectar → Não conectado', /Não conectado/.test(st), st);
  await snap('desconectado');

  // reconectar (para ter provedor na sessão seguinte)
  await card2.getByLabel('URL base').fill('http://localhost:8765/v1');
  await card2.getByLabel('Chave da API').fill(CHAVE);
  await card2.getByRole('button', { name: 'Testar e conectar' }).click();
  await esperar(1500);
  ok('reconectar funciona', /Conectado/.test(await card2.locator('.cfg-status').innerText()) && !/Não conectado/.test(await card2.locator('.cfg-status').innerText()));

  // 6. Sair → Entrar
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await esperar(800);
  await sairPelaUI();
  ok('Sair volta para Entrar', true);
  await snap('saiu');
  await page.getByLabel('E-mail').fill(email);
  await page.getByLabel('Senha').fill(senha);
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await page.waitForFunction(() => !document.body.innerText.includes('Entrar na Sora'), null, { timeout: 10000 });
  await esperar(800);
  ok('Entrar de novo leva ao app (sem onboarding: já tem provedor)', !(await page.getByRole('heading', { name: /conecte sua primeira API/i }).isVisible().catch(() => false)));
  await snap('entrou-de-novo');

  // 7. armazenamento do navegador
  const store = await page.evaluate(async () => {
    const out = { local: {}, session: {}, idb: [] };
    for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); out.local[k] = localStorage.getItem(k); }
    for (let i = 0; i < sessionStorage.length; i++) { const k = sessionStorage.key(i); out.session[k] = sessionStorage.getItem(k); }
    try { const dbs = await indexedDB.databases(); out.idb = dbs.map(d => d.name); } catch {}
    return out;
  });
  const tudo = JSON.stringify(store);
  ok('chave de API ausente em localStorage/sessionStorage', !tudo.includes(CHAVE) && !tudo.includes(ERRADA) && !/sk-[A-Za-z0-9_-]{8,}/.test(tudo));
  ok('IndexedDB vazio', store.idb.length === 0, JSON.stringify(store.idb));
  const cookies = await ctx.cookies();
  ok('cookie de renovação é httpOnly', cookies.filter(c => /renov|refresh/i.test(c.name)).every(c => c.httpOnly), JSON.stringify(cookies.map(c => ({ n: c.name, h: c.httpOnly, p: c.path, s: c.sameSite }))));
  console.log('localStorage keys:', Object.keys(store.local).join(', '));
  console.log('sessionStorage keys:', Object.keys(store.session).join(', '));

  // 8. rede: chave nas respostas?
  const vazou = respostas.filter(r => r.corpo.includes(CHAVE) || r.corpo.includes(ERRADA));
  ok('nenhuma RESPOSTA do backend contém a chave', vazou.length === 0, vazou.map(r => r.url).join(','));
  const pedidosComChave = pedidos.filter(p => p.corpo.includes(CHAVE)).map(p => `${p.metodo} ${new URL(p.url).pathname}`);
  console.log('pedidos que carregam a chave (esperado só POST /v1/provedores…):', [...new Set(pedidosComChave)].join(', '));
  ok('chave só viaja em POST/PATCH de provedores', pedidosComChave.every(p => /\/v1\/provedores/.test(p)), pedidosComChave.join(','));
  const ruins = respostas.filter(r => r.status >= 400).map(r => `${r.status} ${new URL(r.url).pathname}`);
  console.log('respostas >=400:', ruins.join(' | '));
  const campos = new Set();
  for (const r of respostas) if (r.url.includes('/v1/provedores') || r.url.includes('/v1/modelos')) { try { const j = JSON.parse(r.corpo); (function walk(o) { if (o && typeof o === 'object') for (const [k, v] of Object.entries(o)) { campos.add(k); walk(v); } })(j); } catch {} }
  console.log('campos das respostas /provedores e /modelos:', [...campos].join(','));
  const inesperados = consoleErros.filter(e => !/status of (4\d\d)/.test(e));
  ok('console sem erros inesperados', inesperados.length === 0, inesperados.join(' || '));
  console.log('console 4xx esperados:', consoleErros.filter(e => /status of 4/.test(e)).length);
} catch (e) {
  ok('execução sem exceção', false, e.message.split('\n')[0]);
  await snap('ERRO').catch(() => {});
} finally {
  await browser.close();
}
const falhas = resultados.filter(r => !r.ok);
console.log(`\n${W}px: ${resultados.length - falhas.length}/${resultados.length} ok`);
process.exit(falhas.length ? 1 : 0);
