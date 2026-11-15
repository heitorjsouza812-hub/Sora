import assert from 'node:assert/strict';
import { deflateSync } from 'node:zlib';
import { expect } from '@playwright/test';

// Verificações de tela da conversa que o modelo falso não produz sozinho (fontes, imagem na resposta, âncora da busca).
// Só chamadas pelo E2E quando o .env confirma o modelo falso. As rotas são as reais.

// PNG de verdade (gradiente) para o anexo da resposta, sem depender de arquivo no disco.
function pngDeTeste(largura = 360, altura = 220) {
  const linhas = Buffer.alloc((largura * 3 + 1) * altura);
  for (let y = 0; y < altura; y++) {
    const base = y * (largura * 3 + 1);
    for (let x = 0; x < largura; x++) {
      linhas[base + 1 + x * 3] = (60 + (x * 160) / largura) | 0;
      linhas[base + 2 + x * 3] = (90 + (y * 120) / altura) | 0;
      linhas[base + 3 + x * 3] = 200;
    }
  }
  const tabela = [];
  for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; tabela[n] = c >>> 0; }
  const crc = buf => { let r = 0xffffffff; for (const b of buf) r = tabela[(r ^ b) & 0xff] ^ (r >>> 8); return (r ^ 0xffffffff) >>> 0; };
  const bloco = (tipo, dados) => {
    const t = Buffer.concat([Buffer.from(tipo), dados]);
    const tam = Buffer.alloc(4); tam.writeUInt32BE(dados.length);
    const c = Buffer.alloc(4); c.writeUInt32BE(crc(t));
    return Buffer.concat([tam, t, c]);
  };
  const cab = Buffer.alloc(13); cab.writeUInt32BE(largura, 0); cab.writeUInt32BE(altura, 4); cab[8] = 8; cab[9] = 2;
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), bloco('IHDR', cab), bloco('IDAT', deflateSync(linhas)), bloco('IEND', Buffer.alloc(0))]);
}

const FONTES_QA = [
  { n: 1, titulo: 'Guia de cafés especiais', url: 'https://example.com/guia-cafes', dominio: 'example.com' },
  { n: 2, titulo: 'Relatório do setor', url: 'https://example.org/relatorio', dominio: 'example.org' },
];

/**
 * O modelo falso não busca na web nem gera imagem, então a resposta real do servidor ganha fontes e um anexo
 * (enviado de verdade para /v1/anexos) por interceptação da leitura. O que se confere é a tela: chips, [n], imagem, menu.
 */
export async function conferirFontesEAnexos({ page, contexto, base, auth, bot, fotos }) {
  const resposta = await contexto.request.post(`${base}/v1/anexos`, { headers: auth, multipart: { arquivo: { name: 'imagem-qa.png', mimeType: 'image/png', buffer: pngDeTeste() } } });
  assert.ok(resposta.ok(), 'upload do anexo de QA');
  const anexo = await resposta.json();
  const padrao = /\/v1\/conversas\/[^/]+\/mensagens(\?.*)?$/;
  const rota = async route => {
    if (route.request().method() !== 'GET') { await route.continue(); return; }
    const original = await route.fetch();
    const lista = await original.json();
    const ultima = [...lista].reverse().find(m => m.autor !== 'usuario');
    if (ultima) {
      ultima.conteudo = `${ultima.conteudo}\n\nSegundo o guia [1] e o relatório [2], o resultado se mantém.`;
      ultima.fontes = FONTES_QA;
      ultima.anexos = [{ id: anexo.anexo_id, nome: anexo.nome, tipo: anexo.tipo, tamanho: anexo.tamanho }];
    }
    await route.fulfill({ response: original, json: lista });
  };
  await page.route(padrao, rota);
  await page.goto(`${base}/bots/${bot.id}`, { waitUntil: 'domcontentloaded' });
  const chips = page.locator('nav.msg-fontes a');
  await chips.first().waitFor({ timeout: 20_000 });
  assert.equal(await chips.count(), 2, 'dois chips de fonte');
  assert.equal(await chips.first().getAttribute('target'), '_blank');
  assert.equal(await chips.first().getAttribute('href'), 'https://example.com/guia-cafes');
  // chip da etapa 6: número em círculo + domínio; o título da página vai no title e no nome acessível
  assert.match(await chips.first().innerText(), /^1\s*example\.com$/);
  assert.equal(await chips.first().getAttribute('title'), 'Guia de cafés especiais');
  assert.match(await chips.first().getAttribute('aria-label'), /Guia de cafés especiais/);
  const marca = page.locator('.msg-corpo a.fonte-marca', { hasText: /^1$/ }).first();
  await marca.waitFor({ timeout: 10_000 });
  assert.match(await marca.getAttribute('href'), /^#fonte-/, '[1] vira link para a fonte');
  const imagem = page.locator('.msg-imagem img').first();
  await imagem.waitFor({ timeout: 20_000 });
  await expect.poll(() => imagem.evaluate(el => el.naturalWidth)).toBeGreaterThan(100);
  await page.getByRole('link', { name: /Baixar imagem-qa\.png/ }).waitFor();
  const ultima = page.locator('.chat-msg.is-assistant').last();
  // No celular as ações moram atrás do botão "Mais ações"; no computador aparecem ao passar o mouse.
  if (await ultima.getByRole('button', { name: 'Mais ações' }).isVisible()) await ultima.getByRole('button', { name: 'Mais ações' }).click(); else await ultima.hover();
  await page.getByRole('button', { name: 'Boa resposta', exact: true }).last().waitFor({ state: 'visible' });
  if (fotos) await fotos('bot-fontes-imagem-menu');
  await page.locator('button.msg-imagem').first().click();
  await expect(page.locator('dialog.msg-imagem-ampliada')).toBeVisible();
  if (fotos) await fotos('bot-imagem-ampliada');
  await page.keyboard.press('Escape');
  await expect(page.locator('dialog.msg-imagem-ampliada')).toBeHidden();
  // Recarregar mantém tudo: a persistência vem da rota de mensagens, não do estado local.
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.locator('nav.msg-fontes a')).toHaveCount(2, { timeout: 20_000 });
  await page.unroute(padrao, rota);
  console.log('Conversa: fontes numeradas, [n] em link, imagem na resposta com ampliar/baixar e menu da mensagem aprovados.');
}

/** Conversa por voz: sem chave da OpenAI o botão avisa, sem pedir microfone nem gravar nada. */
export async function conferirVozSemChave({ page, base, bot }) {
  await page.goto(`${base}/bots/${bot.id}`, { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Conversar por voz', exact: true }).click();
  await page.getByRole('alert').filter({ hasText: 'conecte uma chave da OpenAI' }).waitFor({ timeout: 10_000 });
  await expect(page.getByRole('button', { name: 'Conversar por voz', exact: true })).toBeVisible();
  console.log('Conversa: voz contínua avisa quando não há chave de voz.');
}

/**
 * Âncora #msg-<id>: manda mensagens suficientes para a primeira sair da primeira página (50), acha a mensagem pela
 * busca real (GET /v1/busca) e abre a rota com o hash. A tela precisa carregar anteriores, rolar e destacar.
 */
export async function conferirAncora({ page, contexto, base, auth, bot, fotos }) {
  await page.goto(`${base}/bots/${bot.id}`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(id => !!window.__sora?.lerEstado().agentes[id]?.conversaId, bot.id);
  const conversaId = await page.evaluate(id => window.__sora.lerEstado().agentes[id].conversaId, bot.id);
  const contar = async () => (await (await contexto.request.get(`${base}/v1/conversas/${conversaId}/mensagens?limite=100`, { headers: auth })).json()).length;
  const alvo = 'pergunta ancorada zebra';
  const enviar = async texto => {
    const r = await contexto.request.post(`${base}/v1/conversas/${conversaId}/mensagens`, { headers: auth, data: { texto, anexos: [], para_agente_id: null } });
    assert.ok(r.ok(), `envio ${r.status()}`);
  };
  let esperado = await contar();
  await enviar(alvo); esperado += 2;
  await expect.poll(contar, { timeout: 60_000 }).toBe(esperado);
  for (let i = 0; i < 27; i++) { await enviar(`enchimento ${i}`); esperado += 2; await expect.poll(contar, { timeout: 60_000 }).toBe(esperado); }
  const achados = await (await contexto.request.get(`${base}/v1/busca?q=${encodeURIComponent(alvo)}`, { headers: auth })).json();
  const achado = achados.resultados.find(r => r.autor === 'usuario');
  assert.ok(achado, 'busca acha a pergunta antiga');
  await page.goto(`${base}/bots/${bot.id}#msg-${achado.mensagem_id}`, { waitUntil: 'domcontentloaded' });
  const alvoMsg = page.locator(`[data-msg-id="${achado.mensagem_id}"]`);
  await alvoMsg.waitFor({ state: 'attached', timeout: 30_000 });
  await expect(alvoMsg).toHaveClass(/msg-destaque/, { timeout: 10_000 });
  await expect(alvoMsg).toBeInViewport({ timeout: 10_000 });
  if (fotos) await fotos('bot-ancora-destaque');
  await expect(alvoMsg).not.toHaveClass(/msg-destaque/, { timeout: 8_000 });
  console.log('Conversa: #msg-<id> carregou anteriores, rolou até a mensagem e a destacou.');
}
