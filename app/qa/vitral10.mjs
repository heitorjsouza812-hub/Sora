// Vitral-10: ao vivo. (1) Resposta direta encerra o turno: o botão volta a Enviar. (2) Cartão de rascunho de bot com
// descrição longa não vaza em 1440 e 390 px. Precisa de API + worker + Vite.
//   SORA_QA_BASE=http://localhost:5173 SORA_QA_EMAIL=vitral10@sora.local node qa/vitral10.mjs
import { chromium } from '@playwright/test';
import { entrarNoContexto, BASE } from './entrar.mjs';

const OUT = new URL('./shots/vitral10/', import.meta.url).pathname.replace(/^\/([A-Z]:)/, '$1');
const LONGA = 'Acompanha concorrentes de cafeterias de bairro, lê diariamente os perfis públicos, resume lançamentos e promoções e escreve um relatório semanal em português claro com sugestões de ações para a equipe de marketing, sempre citando a fonte de cada informação encontrada na internet. ';
const nav = await chromium.launch();
const falhas = [];
for (const [nome, w, h] of [['1440', 1440, 900], ['390', 390, 844]]) {
  const ctx = await nav.newContext({ viewport: { width: w, height: h } });
  await entrarNoContexto(ctx);
  const page = await ctx.newPage();
  page.on('pageerror', e => falhas.push(`${nome}: ${e.message}`));
  await page.goto(BASE + '/'); await page.waitForTimeout(2500);

  // 1) pedido simples (resposta direta) de verdade; o botão tem de voltar a "Enviar" logo após a resposta
  const campo = page.getByRole('textbox').first();
  await campo.fill('Qual é a capital da França?'); await campo.press('Enter');
  const t0 = Date.now(); let voltou = null;
  while (Date.now() - t0 < 60_000) {
    const parar = await page.getByRole('button', { name: /^Parar/ }).count();
    const resposta = await page.getByText(/Paris/).count();
    if (resposta && !parar) { voltou = Date.now() - t0; break; }
    await page.waitForTimeout(500);
  }
  await page.waitForTimeout(3000);
  const aindaParar = await page.getByRole('button', { name: /^Parar/ }).count();
  const pensando = await page.getByText(/está pensando/i).count();
  console.log(nome, 'resposta+Enviar em', voltou, 'ms; Parar depois de 3 s:', aindaParar, '; "pensando":', pensando);
  if (voltou === null) console.log(nome, 'AVISO: sem resposta (conta de QA sem provedor ou cota esgotada); coberto por teste de redutor');
  else if (aindaParar || pensando) falhas.push(`${nome}: a conversa não saiu de "pensando"`);
  await page.screenshot({ path: `${OUT}resposta-direta-${nome}.png` });

  // 2) rascunho longo (GET interceptado só neste QA) + evento bot.rascunho
  await page.route('**/v1/bots/rascunhos', r => r.request().method() === 'GET'
    ? r.fulfill({ json: [{ id: 'r-long', nome: 'Observador de concorrentes', funcao: LONGA, cor: '#46E8A8', instrucoes: LONGA, ferramentas: [], rotina: null, status: 'rascunho' }] })
    : r.continue());
  await page.evaluate(() => window.__sora.injetarEvento({ id: `${Date.now()}-0`, tipo: 'bot.rascunho', dados: {}, recebidoEm: Date.now() }));
  await page.waitForSelector('.bot-draft-card', { timeout: 8000 });
  await page.waitForTimeout(600);
  const m = await page.evaluate(() => {
    const c = document.querySelector('.bot-draft-card').getBoundingClientRect();
    const fora = [...document.querySelectorAll('.bot-draft-card *')].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.right > c.right + 1 || r.left < c.left - 1); }).map(e => e.className || e.tagName).slice(0, 5);
    return { cartao: [c.left, c.right], janela: innerWidth, rolagemHorizontal: document.documentElement.scrollWidth > innerWidth, fora };
  });
  console.log(nome, 'rascunho', JSON.stringify(m));
  if (m.fora.length || m.rolagemHorizontal) falhas.push(`${nome}: cartão vaza ${JSON.stringify(m)}`);
  await page.locator('.bot-draft-card').scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${OUT}rascunho-longo-${nome}.png` });
  await ctx.close();
}
await nav.close();
console.log(falhas.length ? 'FALHAS:\n' + falhas.join('\n') : 'tudo certo');
process.exit(falhas.length ? 1 : 0);
