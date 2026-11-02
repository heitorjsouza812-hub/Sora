// Digitação rápida nos campos de mensagem (Home, chat do projeto, chat do agente): o valor final tem de
// ser IGUAL ao texto digitado. Não precisa de backend: a API é simulada na camada de rede do navegador
// (login, usuário e listas vazias), então só mede o app. Uso: SORA_QA_BASE=http://localhost:5373 node qa/digitacao.mjs
import { chromium } from '@playwright/test';

const BASE = process.env.SORA_QA_BASE ?? 'http://localhost:5173';
const TEXTO = 'o domínio example.com e o exemplo, com um pesquisador, citando a página; oque mais? psquisador exampl.com itando '.repeat(2).trim();
const usuario = { nome: 'QA', email: 'qa@sora.local', prioridade: 'qualidade', tem_provedor: true };

async function simularApi(page) {
  await page.route('**/v1/**', route => {
    const url = new URL(route.request().url());
    const json = (corpo, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(corpo) });
    if (url.pathname === '/v1/auth/renovar') return json({ token_acesso: 'x' });
    if (url.pathname === '/v1/eu') return json(usuario);
    if (url.pathname === '/v1/eventos' || url.pathname.endsWith('/eventos')) return route.fulfill({ status: 200, contentType: 'text/event-stream', body: ': ok\n\n' });
    if (url.pathname === '/v1/conversas' || url.pathname === '/v1/agentes') return json([]);
    if (url.pathname.includes('/uso')) return json({ itens: [], periodo: {} });
    return json({});
  });
}

let falhas = 0;
async function medir(page, rotulo, seletor, atraso) {
  const campo = page.locator(seletor).first();
  await campo.click();
  await campo.fill('');
  await page.keyboard.type(TEXTO, { delay: atraso });
  const valor = await campo.inputValue();
  const ok = valor === TEXTO;
  if (!ok) falhas++;
  console.log(`${ok ? 'ok ' : 'FALHOU'} ${rotulo} delay=${atraso}${ok ? '' : `\n   esperado: ${TEXTO}\n   obtido:   ${valor}`}`);
}

const navegador = await chromium.launch();
for (const [largura, altura] of [[1440, 900], [390, 844]]) {
  const contexto = await navegador.newContext({ viewport: { width: largura, height: altura }, colorScheme: 'dark' });
  const page = await contexto.newPage();
  await simularApi(page);
  page.on('pageerror', e => console.log('pageerror', '', String(e.stack).split(String.fromCharCode(10)).slice(0,12).join(' | ')));
  page.on('console', m => { if (m.type() === 'error') console.log('console', m.text().slice(0, 900)); });
  await page.goto(`${BASE}/`);
  await page.evaluate(() => sessionStorage.setItem('sora.chegou', '1'));
  await page.reload();
  const campo = 'textarea[aria-label^="Peça qualquer coisa"]';
  await page.waitForSelector(campo, { timeout: 20_000 });
  for (const atraso of [0, 5]) await medir(page, `Home ${largura}`, campo, atraso);
  await contexto.close();
}
await navegador.close();
if (falhas) { console.log(`\n${falhas} falha(s)`); process.exit(1); }
console.log('\nDigitação íntegra');
