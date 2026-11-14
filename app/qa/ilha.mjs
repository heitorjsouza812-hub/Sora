// Etapa 5: "Ilha só fora do app" — a <Ilha/> só existe na janela dedicada do app de desktop
// (app/src/components/ilha/IlhaDesktop.tsx), mostrada/escondida pelo Rust conforme o foco da janela
// "main" (app/src-tauri/src/lib.rs). Dentro do app web ela nunca chega a montar conteúdo visível.
//
// Este script prova a parte automatizável sem um binário do Tauri: que a Ilha NÃO aparece em
// nenhuma tela do app comum (web), mesmo depois de criar um bot e ele entrar em "trabalhando"/
// "precisa de você" — nenhuma pílula, nenhum diálogo "Ilha da Sora", nenhum CSS/JS da ilha carregado.
//
// O comportamento "aparece fora de foco, some em foco" é de janela nativa (Tauri real) e não dá
// para simular num browser comum; a verificação manual é a do app/docs/sora-desktop.md §3
// (Validação): `npm run desktop`, minimizar/trocar de janela e observar a pílula aparecer no topo
// da tela, depois voltar o foco para a Sora e observar ela desaparecer.
import assert from 'node:assert/strict';
import { mkdir, readdir, rm } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
// entrar.mjs lê SORA_QA_BASE ao ser importado: fixa a porta desta etapa antes de importá-lo.
process.env.SORA_QA_BASE ??= 'http://localhost:5383';
const { entrarNoContexto } = await import('./entrar.mjs');

const BASE = process.env.SORA_QA_BASE ?? 'http://localhost:5383';
const qaDir = dirname(fileURLToPath(import.meta.url));
const shotsDir = join(qaDir, 'shots', 'ilha');
const erros = [];

await mkdir(shotsDir, { recursive: true });
await Promise.all((await readdir(shotsDir)).filter(a => a.endsWith('.png')).map(a => rm(join(shotsDir, a))));

const browser = await chromium.launch({ headless: true });
const contexto = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' });
await entrarNoContexto(contexto, {
  email: process.env.SORA_QA_ILHA_EMAIL ?? 'qa-ilha-e5@sora.local',
});
const page = await contexto.newPage();
page.on('console', m => { if (m.type() === 'error') erros.push({ tipo: 'console', texto: m.text(), url: page.url() }); });
page.on('pageerror', e => erros.push({ tipo: 'pageerror', texto: e.message, url: page.url() }));
const snap = nome => page.screenshot({ path: join(shotsDir, nome), fullPage: false });

/** Nada da ilha deve existir no DOM desta tela: nem a pílula, nem o diálogo expandido. */
async function semIlhaNestaTela(rotulo) {
  await expectAusente(page.getByRole('button', { name: /^Ilha da Sora:/i }), `pílula da ilha em ${rotulo}`);
  await expectAusente(page.getByRole('dialog', { name: 'Ilha da Sora', exact: true }), `painel da ilha em ${rotulo}`);
  assert.equal(await page.locator('.ilha-ancora').count(), 0, `nenhum nó .ilha-ancora deveria existir em ${rotulo} (web não renderiza a ilha)`);
}
async function expectAusente(locator, descricao) {
  assert.equal(await locator.count(), 0, `${descricao} não deveria existir no app web`);
}

// Limpeza: a conversa que este teste abre com a Sora (e o pedido pendente dela) é apagada no fim,
// para a conta de QA não acumular nada entre execuções.
const API = process.env.SORA_QA_API ?? 'http://localhost:8200';
const EMAIL_QA = process.env.SORA_QA_ILHA_EMAIL ?? 'qa-ilha-e5@sora.local';
async function tokenQa() {
  const r = await fetch(`${API}/v1/auth/entrar`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: EMAIL_QA, senha: process.env.SORA_QA_SENHA ?? 'sora-qa-senha-123' }) });
  return r.ok ? (await r.json()).token_acesso : null;
}
async function idsConversas(token) {
  const r = await fetch(`${API}/v1/conversas`, { headers: { Authorization: `Bearer ${token}` } });
  return r.ok ? (await r.json()).map(c => c.id) : [];
}
async function idsAtencao(token) {
  const r = await fetch(`${API}/v1/atencao`, { headers: { Authorization: `Bearer ${token}` } });
  return r.ok ? (await r.json()).map(p => p.id) : [];
}
const tokenLimpeza = await tokenQa();
const conversasAntes = new Set(tokenLimpeza ? await idsConversas(tokenLimpeza) : []);
const atencaoAntes = new Set(tokenLimpeza ? await idsAtencao(tokenLimpeza) : []);

let falha;
try {
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 30_000 });
  const compositor = page.getByRole('textbox', { name: /Mensagem para a Sora|Peça qualquer coisa à Sora/i });
  await compositor.waitFor({ state: 'visible', timeout: 15_000 });
  await snap('01-home-sem-ilha-1440x900.png');
  await semIlhaNestaTela('Home');

  // Pede um bot que já nasce ocupado (o modelo falso entende "[aprovacao]" como pedido de atenção
  // pendente); mesmo com um bot "trabalhando"/"precisa de você" de verdade, a ilha não aparece no web.
  await compositor.fill('crie um bot revisor de textos [aprovacao]');
  await page.getByRole('button', { name: 'Enviar mensagem', exact: true }).click();
  await page.waitForTimeout(3_000);
  await snap('02-apos-pedido-sem-ilha-1440x900.png');
  await semIlhaNestaTela('depois de um pedido que deixa um bot pendente');

  // Atalho Ctrl/⌘+Shift+S: no web não deve desenhar nada — a <Ilha/> só existe na janela "ilha" do
  // Tauri (o AppShell não a monta mais).
  await page.keyboard.press('Control+Shift+S');
  await page.waitForTimeout(300);
  await semIlhaNestaTela('depois do atalho Ctrl+Shift+S');

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(300);
  await snap('03-celular-sem-ilha-390x844.png');
  await semIlhaNestaTela('celular (390px)');

  assert.deepEqual(erros, [], `console limpo:\n${JSON.stringify(erros, null, 2)}`);
} catch (erro) {
  falha = erro;
  try { await snap('FALHA.png'); } catch { /* página encerrada */ }
} finally {
  await contexto.close();
  await browser.close();
  if (tokenLimpeza) {
    // apagar a conversa não resolve a aprovação pendente dela: recusa antes o que este teste abriu
    for (const id of (await idsAtencao(tokenLimpeza)).filter(id => !atencaoAntes.has(id))) {
      await fetch(`${API}/v1/aprovacoes/${id}/decidir`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tokenLimpeza}` }, body: JSON.stringify({ decisao: 'negar' }) });
    }
    for (const id of (await idsConversas(tokenLimpeza)).filter(id => !conversasAntes.has(id))) {
      const r = await fetch(`${API}/v1/conversas/${id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${tokenLimpeza}` } });
      if (r.status !== 204) console.error(`aviso: não consegui apagar a conversa de QA ${id} (${r.status})`);
    }
  }
}

if (falha || erros.length) {
  if (falha) console.error(`FALHA Ilha (etapa 5): ${falha.stack ?? falha.message}`);
  for (const erro of erros) console.error(`CONSOLE [${erro.tipo}] ${erro.texto}`);
  process.exitCode = 1;
} else {
  console.log('Ilha (etapa 5) aprovada: nenhuma pílula/painel aparece no app web, nem com um bot pendente, nem pelo atalho; console limpo.');
  console.log('Comportamento de janela nativa (aparece fora de foco, some em foco): rode qa/ilha-tauri.mjs com o app de desktop aberto.');
}
