// Fotos do "antes" para a especificação visual da etapa 6. Não altera o app; usa conta de QA própria.
import { mkdir } from 'node:fs/promises';
import { deflateSync } from 'node:zlib';

const APP = 'file:///C:/dev/sora-e5/app/';
const BASE = 'http://localhost:5383';
process.env.SORA_QA_BASE = BASE;
const { chromium } = await import(`${APP}node_modules/@playwright/test/index.mjs`);
const { entrarNoContexto } = await import(`${APP}qa/entrar.mjs`);
const SHOTS = 'C:/dev/sora-e5/app/qa/shots/design';
const PREFIXO = process.env.SORA_DESIGN_PREFIXO ?? 'antes';
await mkdir(SHOTS, { recursive: true });

const so = process.argv[2] ? process.argv[2].split(',') : null;
const browser = await chromium.launch({ headless: true });
const email = process.env.SORA_DESIGN_EMAIL ?? 'qa-design@sora.local';
const desk = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' });
const sessao = await entrarNoContexto(desk, { email, limparConversas: !so });
const auth = { Authorization: `Bearer ${sessao.token_acesso}` };
const cel = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: 'dark', hasTouch: true, deviceScaleFactor: 2 });
await entrarNoContexto(cel, { email });

const api = async (metodo, caminho, data) => {
  const r = await desk.request[metodo](`${BASE}${caminho}`, { headers: auth, data, failOnStatusCode: false });
  const corpo = await r.json().catch(() => null);
  return { status: r.status(), corpo };
};
if (!so) {
  for (const g of (await api('get', '/v1/grupos')).corpo ?? []) await api('post', `/v1/canais-equipe/${g.id}/arquivar`);
  for (const p of (await api('get', '/v1/grupos/propostas')).corpo ?? []) await api('post', `/v1/grupos/propostas/${p.id}/recusar`);
}

const d = await desk.newPage();
const m = await cel.newPage();
const erros = [];
for (const [nome, p] of [['1440', d], ['390', m]]) p.on('pageerror', e => erros.push(`${nome}: ${e.message}`));

const foto = (p, nome) => p.screenshot({ path: `${SHOTS}/${PREFIXO}-${nome}-${p === d ? '1440' : '390'}.png` });
const passo = async (nome, fn) => {
  if (so && !so.some(s => nome.startsWith(s))) return;
  try { await fn(); console.log('ok   ', nome); } catch (e) { console.log('FALHA', nome, '-', String(e.message).split('\n')[0]); }
};
const ir = async (p, caminho, espera = 1200) => { await p.goto(`${BASE}${caminho}`, { waitUntil: 'domcontentloaded' }); await p.waitForTimeout(espera); };
// A central "Precisa de você" saiu da barra lateral: abre pelo comando da paleta (Ctrl+K).
const abrirCentral = async p => {
  if (p === m) { await p.getByRole('button', { name: 'Abrir menu' }).click(); await p.waitForTimeout(400); await p.getByRole('button', { name: /Buscar/ }).click(); } else await p.keyboard.press('Control+k');
  await p.waitForTimeout(500); await p.keyboard.type('Precisa de você'); await p.waitForTimeout(300); await p.keyboard.press('Enter'); await p.waitForTimeout(700);
};
const enviar = async (p, texto, espera = 7000) => {
  const campo = p.getByRole('textbox').last();
  await campo.fill(texto);
  await campo.press('Enter');
  await p.waitForTimeout(espera);
};

function png(largura = 720, altura = 440) {
  const linhas = Buffer.alloc((largura * 3 + 1) * altura);
  for (let y = 0; y < altura; y++) { const b = y * (largura * 3 + 1); for (let x = 0; x < largura; x++) { linhas[b + 1 + x * 3] = (20 + (x * 60) / largura) | 0; linhas[b + 2 + x * 3] = (28 + (y * 50) / altura) | 0; linhas[b + 3 + x * 3] = (60 + (x * 80) / largura) | 0; } }
  const t = []; for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
  const crc = buf => { let r = 0xffffffff; for (const b of buf) r = t[(r ^ b) & 0xff] ^ (r >>> 8); return (r ^ 0xffffffff) >>> 0; };
  const bloco = (tipo, dados) => { const x = Buffer.concat([Buffer.from(tipo), dados]); const tam = Buffer.alloc(4); tam.writeUInt32BE(dados.length); const c = Buffer.alloc(4); c.writeUInt32BE(crc(x)); return Buffer.concat([tam, x, c]); };
  const cab = Buffer.alloc(13); cab.writeUInt32BE(largura, 0); cab.writeUInt32BE(altura, 4); cab[8] = 8; cab[9] = 2;
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), bloco('IHDR', cab), bloco('IDAT', deflateSync(linhas)), bloco('IEND', Buffer.alloc(0))]);
}

// ---------- estado vazio ----------
await passo('01-sora-vazia', async () => {
  for (const p of [d, m]) { await ir(p, '/', 2500); await foto(p, '01-sora-vazia'); }
  await d.getByRole('textbox', { name: 'Mensagem para a Sora…' }).fill('Quero um bot que acompanhe os preços dos meus concorrentes');
  await d.waitForTimeout(900); await foto(d, '01b-sora-vazia-digitando');
  await d.getByRole('textbox', { name: 'Mensagem para a Sora…' }).fill('');
  await m.getByRole('textbox', { name: 'Mensagem para a Sora…' }).fill('Quero um bot que acompanhe preços');
  await m.waitForTimeout(900); await foto(m, '01b-sora-vazia-digitando');
  await m.getByRole('textbox', { name: 'Mensagem para a Sora…' }).fill('');
});
await passo('10-paleta', async () => {
  await ir(d, '/'); await d.keyboard.press('Control+k'); await d.waitForTimeout(700); await foto(d, '10-paleta'); await d.keyboard.press('Escape');
  await ir(m, '/'); await m.getByRole('button', { name: 'Abrir menu' }).click(); await m.waitForTimeout(700); await foto(m, '13-menu');
  await m.getByRole('button', { name: /Buscar/ }).click(); await m.waitForTimeout(700); await foto(m, '10-paleta'); await m.keyboard.press('Escape');
});
await passo('09a-central-vazia', async () => {
  await ir(d, '/'); await abrirCentral(d); await foto(d, '09a-central-vazia'); await d.keyboard.press('Escape');
});
await passo('12a-bots-vazio', async () => { for (const p of [d, m]) { await ir(p, '/bots'); await foto(p, '12a-bots-vazio'); } });
await passo('05a-grupos-vazio', async () => { for (const p of [d, m]) { await ir(p, '/grupos'); await foto(p, '05a-grupos-vazio'); } });

// ---------- rascunho e bots ----------
const nomes = ['Bot de pesquisa', 'Bot de textos'];
await passo('07-rascunho', async () => {
  await ir(d, '/'); await ir(m, '/');
  for (const [i, nome] of nomes.entries()) {
    const r = await api('post', '/v1/bots/rascunhos', { descricao: `${nome}: organize informações com objetividade` });
    if (r.status >= 300) throw new Error(`rascunho ${r.status} ${JSON.stringify(r.corpo)}`);
    const cartao = d.getByRole('article', { name: /Rascunho do bot/i }).last();
    await cartao.waitFor({ state: 'visible', timeout: 20000 });
    await cartao.getByLabel('Nome').fill(nome);
    if (i === 0) {
      await d.waitForTimeout(500); await foto(d, '07-rascunho-bot');
      await cartao.scrollIntoViewIfNeeded(); await d.screenshot({ path: `${SHOTS}/${PREFIXO}-07b-rascunho-bot-inteiro-1440.png`, fullPage: true });
      await m.reload({ waitUntil: 'domcontentloaded' }); await m.waitForTimeout(2500); await foto(m, '07-rascunho-bot');
      await m.locator('.conversation-scroll').evaluate(el => { el.scrollTop = el.scrollHeight; }).catch(() => undefined);
      await m.waitForTimeout(400); await foto(m, '07b-rascunho-bot-fim');
    }
    await cartao.getByRole('button', { name: 'Criar bot' }).click();
    await d.getByText('Bot criado', { exact: true }).last().waitFor({ state: 'visible', timeout: 20000 });
    if (i === 0) { await d.waitForTimeout(600); await foto(d, '07c-bot-criado'); }
  }
});
const bots = ((await api('get', '/v1/agentes')).corpo ?? []).filter(a => nomes.includes(a.nome));
const bot = bots.find(b => b.nome === nomes[0]);
console.log('bots:', bots.map(b => `${b.nome}=${b.id}`).join(' '));

// ---------- conversa com a Sora ----------
await passo('02-sora-conversa', async () => {
  await ir(d, '/');
  await enviar(d, 'Explique em tópicos como organizar a minha semana de trabalho', 9000);
  await foto(d, '02-sora-conversa');
  await ir(m, '/', 2500); await foto(m, '02-sora-conversa');
  // "pensando": foto logo depois do envio
  const campo = d.getByRole('textbox').last(); await campo.fill('E como priorizar as tarefas?'); await campo.press('Enter');
  await d.waitForTimeout(450); await foto(d, '02b-sora-pensando'); await d.waitForTimeout(1200); await foto(d, '02c-sora-gerando');
  await d.waitForTimeout(8000);
});

// ---------- bot: fontes, imagem, menu, painel Trabalho ----------
await passo('03-bot', async () => {
  if (!bot) throw new Error('sem bot');
  await ir(d, `/bots/${bot.id}`, 2000); await foto(d, '03a-bot-vazio');
  await ir(m, `/bots/${bot.id}`, 2000); await foto(m, '03a-bot-vazio');
  await enviar(d, 'Pesquise as tendências do setor e resuma em uma tabela', 10000);
  await foto(d, '03b-bot-resposta');
  const up = await desk.request.post(`${BASE}/v1/anexos`, { headers: auth, multipart: { arquivo: { name: 'grafico.png', mimeType: 'image/png', buffer: png() } } });
  const anexo = await up.json();
  const padrao = /\/v1\/conversas\/[^/]+\/mensagens(\?.*)?$/;
  const rota = async route => {
    if (route.request().method() !== 'GET') { await route.continue(); return; }
    const original = await route.fetch(); const lista = await original.json();
    const ultima = [...lista].reverse().find(x => x.autor !== 'usuario');
    if (ultima) {
      ultima.conteudo = '## Resumo\n\nO setor cresceu de forma **constante** no período, segundo o levantamento [1] e o relatório [2].\n\n- Primeiro ponto do resumo, com uma frase de tamanho normal para ver a quebra de linha na coluna de leitura.\n- Segundo ponto, mais curto.\n- Terceiro ponto.\n\n| Item | Antes | Depois |\n|---|---|---|\n| Linha A | 10 | 14 |\n| Linha B | 22 | 25 |\n\n```python\ntotal = sum(valores)\nprint(total)\n```\n\nPosso detalhar qualquer um dos pontos.';
      ultima.fontes = [
        { n: 1, titulo: 'Levantamento do setor', url: 'https://example.com/levantamento', dominio: 'example.com' },
        { n: 2, titulo: 'Relatório anual', url: 'https://example.org/relatorio', dominio: 'example.org' },
        { n: 3, titulo: 'Página de referência com um título bem comprido para testar', url: 'https://example.net/ref', dominio: 'example.net' },
      ];
      ultima.anexos = [{ id: anexo.anexo_id, nome: anexo.nome, tipo: anexo.tipo, tamanho: anexo.tamanho }];
    }
    await route.fulfill({ response: original, json: lista });
  };
  for (const p of [d, m]) {
    await p.route(padrao, rota);
    await ir(p, `/bots/${bot.id}`, 3500);
    const ultima = p.locator('.chat-msg.is-assistant').last();
    await p.locator('.conversation-scroll').first().evaluate(el => { el.scrollTop = 0; }).catch(() => undefined);
    await p.waitForTimeout(300); await foto(p, '03c-bot-markdown-topo');
    await p.locator('.conversation-scroll').first().evaluate(el => { el.scrollTop = el.scrollHeight; }).catch(() => undefined);
    await p.waitForTimeout(300);
    if (await ultima.getByRole('button', { name: 'Mais ações' }).isVisible().catch(() => false)) await ultima.getByRole('button', { name: 'Mais ações' }).click(); else await ultima.hover();
    await p.waitForTimeout(500); await foto(p, '03d-bot-fontes-imagem-menu');
    await p.screenshot({ path: `${SHOTS}/${PREFIXO}-03e-bot-pagina-inteira-${p === d ? '1440' : '390'}.png`, fullPage: true });
    await p.unroute(padrao, rota);
  }
  // painel Trabalho e Recursos
  await ir(d, `/bots/${bot.id}`, 2500);
  await d.getByRole('tab', { name: 'Trabalho' }).click(); await d.waitForTimeout(500); await foto(d, '04a-bot-painel-trabalho');
  await d.getByRole('tab', { name: 'Recursos' }).click(); await d.waitForTimeout(800); await foto(d, '04b-bot-painel-recursos');
  // menu "…" do bot
  await d.locator('.topbar-identity button').first().click().catch(() => undefined); await d.waitForTimeout(500); await foto(d, '04c-bot-menu'); await d.keyboard.press('Escape');
});
await passo('04m-bot-painel-celular', async () => {
  await ir(m, `/bots/${bot.id}`, 2500);
  const botoes = await m.getByRole('button').evaluateAll(els => els.map(e => e.getAttribute('aria-label') || e.textContent?.trim()).filter(Boolean));
  console.log('   botões no celular (bot):', botoes.join(' | '));
  const abrir = m.getByRole('button', { name: /Trabalho|painel|Detalhes/i }).first();
  if (await abrir.isVisible().catch(() => false)) { await abrir.click(); await m.waitForTimeout(800); await foto(m, '04a-bot-painel-trabalho'); }
});

// ---------- cartão Precisa de você + central ----------
await passo('08-precisa', async () => {
  await ir(d, `/bots/${bot.id}`, 2000);
  await enviar(d, '[aprovacao] ajuste suas instruções', 9000);
  await foto(d, '08a-bot-cartao-precisa');
  await ir(d, '/', 2000);
  await enviar(d, '[pergunta] monte um plano de divulgação', 12000);
  await foto(d, '08b-sora-cartao-pergunta');
  await abrirCentral(d); await d.waitForTimeout(300); await foto(d, '09-central-precisa'); await d.keyboard.press('Escape');
  await foto(d, '09b-barra-lateral-com-pedido');
  await ir(m, `/bots/${bot.id}`, 2500); await foto(m, '08a-bot-cartao-precisa');
  await m.getByRole('button', { name: 'Abrir menu' }).click(); await m.waitForTimeout(600); await foto(m, '13b-menu-com-pedido');
  await m.keyboard.press('Escape'); await m.waitForTimeout(400); await abrirCentral(m); await m.waitForTimeout(300); await foto(m, '09-central-precisa');
});

// ---------- galeria ----------
await passo('12-bots', async () => { for (const p of [d, m]) { await ir(p, '/bots', 1800); await foto(p, '12-bots-galeria'); } });

// ---------- grupos ----------
let grupoId = (((await api('get', '/v1/grupos')).corpo ?? [])[0] ?? {}).id;
await passo('06-grupo', async () => {
  await ir(d, '/grupos', 1500);
  await d.getByRole('button', { name: 'Criar grupo' }).first().click(); await d.waitForTimeout(700);
  const modal = d.getByRole('dialog');
  await modal.getByLabel('Nome do grupo').fill('Grupo de planejamento');
  for (const nome of nomes) await modal.getByText(nome, { exact: true }).click();
  await d.waitForTimeout(400); await foto(d, '06-novo-grupo');
  await ir(m, '/grupos', 1500); await m.getByRole('button', { name: /Novo grupo|Criar grupo/ }).first().click(); await m.waitForTimeout(800); await foto(m, '06-novo-grupo'); await m.keyboard.press('Escape');
  await modal.getByRole('button', { name: 'Criar grupo', exact: true }).click();
  await d.waitForURL(/\/grupos\/[0-9a-f-]+$/i, { timeout: 20000 });
  grupoId = d.url().split('/').pop();
  await d.waitForTimeout(1500); await foto(d, '05b-grupo-sem-mensagens');
});
await passo('05-grupo-mensagens', async () => {
  await ir(d, `/grupos/${grupoId}`, 2000);
  await enviar(d, '@todos Planejem a divulgação da semana e dividam as tarefas', 15000);
  await foto(d, '05c-grupo-mensagens');
  await enviar(d, 'Qual é o próximo passo?', 9000);
  await foto(d, '05d-grupo-mensagens-2');
  await d.screenshot({ path: `${SHOTS}/${PREFIXO}-05e-grupo-pagina-inteira-1440.png`, fullPage: true });
  await d.locator('.grp-head button, [aria-label*="grupo" i]').last().click().catch(() => undefined); await d.waitForTimeout(500); await foto(d, '05f-grupo-menu'); await d.keyboard.press('Escape');
  await ir(m, '/grupos', 1800); await foto(m, '05g-grupos-lista');
  await ir(m, `/grupos/${grupoId}`, 2500); await foto(m, '05c-grupo-mensagens');
  await m.getByRole('textbox').last().fill('@'); await m.waitForTimeout(600); await foto(m, '05h-grupo-mencao');
});

// ---------- configurações ----------
await passo('11-config', async () => {
  for (const p of [d, m]) {
    await ir(p, '/configuracoes', 1800);
    const abas = await p.getByRole('tab').allInnerTexts();
    for (const [i, aba] of abas.entries()) {
      await p.getByRole('tab', { name: aba, exact: true }).click(); await p.waitForTimeout(900);
      const nome = aba.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-');
      await foto(p, `11-config-${String(i + 1).padStart(2, '0')}-${nome}`);
    }
  }
});

console.log('erros de página:', erros.length ? erros : 'nenhum');
await browser.close();
