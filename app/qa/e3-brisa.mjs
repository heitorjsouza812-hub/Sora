// QA da Parte B · Etapa 3 (Brisa): paleta Ctrl+K e atalhos, créditos simulados e Desfazer de chat/projeto.
// Uso: node qa/e3-brisa.mjs   (dev server em http://localhost:5173)
import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const BASE = 'http://localhost:5173';
const out = join(dirname(fileURLToPath(import.meta.url)), 'shots', 'brisa');
await mkdir(out, { recursive: true });
const erros = [];
const ok = (cond, msg) => { if (!cond) erros.push(msg); };
const browser = await chromium.launch();

// ---------- desktop ----------
{
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' })).newPage();
  page.on('pageerror', (e) => erros.push(`pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error') erros.push(`console: ${m.text()}`); });
  await page.goto(`${BASE}/projetos`);
  await page.evaluate(() => { localStorage.clear(); sessionStorage.setItem('sora.chegou', '1'); });
  await page.reload();
  await page.evaluate(() => {
    const s = window.__sora;
    s.criarProjeto('Crie uma campanha de lançamento para minha cafeteria com peças e calendário.', Date.now() - 300_000, { tipo: 'projeto' });
    s.criarProjeto('oi, tudo bem?', Date.now() - 60_000, { tipo: 'chat' });
    s.novoChat();
  });
  await page.waitForTimeout(1200);

  // créditos: rodapé mostra "X de 2.000 créditos" e cobrou o trabalho já feito
  const ind = page.locator('.cr-indicador');
  ok(await ind.isVisible(), 'indicador de créditos não aparece na barra lateral');
  const texto = await ind.innerText();
  ok(/de 2\.000 créditos/.test(texto), `texto do indicador inesperado: ${texto}`);
  const restantes = Number((texto.match(/([\d.]+) de 2\.000/)?.[1] ?? '0').replace(/\./g, ''));
  ok(restantes > 0 && restantes < 1240, `créditos deviam ter sido cobrados pelo projeto (restam ${restantes})`);
  await page.screenshot({ path: join(out, 'e3-creditos.png'), clip: { x: 0, y: 700, width: 300, height: 200 } });

  // aviso < 10%
  await page.evaluate(() => window.__creditos.gastar(5000));
  await page.waitForTimeout(400);
  ok(await page.locator('.b-toast').filter({ hasText: 'créditos acabaram' }).count() === 1, 'aviso de créditos esgotados não apareceu');
  ok(await ind.evaluate((el) => el.classList.contains('is-acabando')), 'indicador não ficou em estado de aviso');
  await page.screenshot({ path: join(out, 'e3-creditos-acabando.png') });
  await page.evaluate(() => window.__creditos.reiniciar());

  // paleta: Ctrl+K abre, busca, setas, Enter navega
  await page.locator('body').click({ position: { x: 900, y: 600 } });
  await page.keyboard.press('Control+k');
  const dialogo = page.getByRole('dialog', { name: 'Paleta de comandos' });
  await dialogo.waitFor({ timeout: 2000 });
  const campo = dialogo.getByRole('combobox');
  ok(await campo.evaluate((el) => el === document.activeElement), 'foco não foi para o campo da paleta');
  ok(await page.locator('.cr-indicador').evaluate((el) => !!el.closest('[inert]')), 'fundo deveria ficar inerte com a paleta aberta');
  await page.waitForTimeout(300);
  await page.screenshot({ path: join(out, 'e3-paleta.png') });
  await campo.fill('camp');
  await page.waitForTimeout(150);
  const opcoes = dialogo.getByRole('option');
  ok(await opcoes.count() >= 1, 'busca "camp" não achou o projeto');
  await page.keyboard.press('ArrowDown');
  const ativo = await campo.getAttribute('aria-activedescendant');
  ok(!!ativo && (await page.locator(`#${ativo}`).getAttribute('aria-selected')) === 'true', 'aria-activedescendant não aponta para a opção selecionada');
  await campo.fill('agentes');
  await page.waitForTimeout(150);
  await campo.fill('criar agente');
  await page.keyboard.press('Enter');
  await page.waitForURL(/\/agentes\/novo/, { timeout: 3000 }).catch(() => erros.push(`Enter não abriu Criar agente: ${page.url()}`));

  // Esc fecha e devolve o foco
  await page.goto(`${BASE}/projetos`);
  await page.waitForTimeout(600);
  await page.keyboard.press('Control+k');
  await dialogo.waitFor({ timeout: 2000 });
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);
  ok(await dialogo.count() === 0, 'Esc não fechou a paleta');

  // '/' foca o campo de mensagem; Ctrl+Shift+O = novo chat
  await page.locator('body').click({ position: { x: 900, y: 650 } });
  await page.keyboard.press('/');
  ok(await page.evaluate(() => document.activeElement?.tagName === 'TEXTAREA'), "'/' não focou o campo de mensagem");
  await page.locator('body').click({ position: { x: 900, y: 650 } });
  await page.keyboard.press('Control+Shift+O');
  await page.waitForTimeout(400);
  ok(new URL(page.url()).pathname === '/', `Ctrl+Shift+O não abriu o novo chat: ${page.url()}`);

  // Desfazer: chat (sem equipe) apaga direto e volta
  await page.goto(`${BASE}/projetos`);
  await page.waitForTimeout(600);
  const contaChats = () => page.evaluate(() => window.__sora.lerEstado().projetos.filter((p) => p.tipo === 'chat').length);
  const antes = await contaChats();
  const linhaChat = page.locator('.sidebar .chat-row').filter({ hasText: /oi, tudo bem|Conversa/i }).first();
  if (await linhaChat.count()) {
    await linhaChat.getByRole('button', { name: /opções/i }).click();
    await page.getByRole('menuitem', { name: 'Apagar', exact: true }).click();
    await page.waitForTimeout(300);
    ok(await page.getByRole('dialog').count() === 0, 'apagar chat sem equipe não deveria pedir confirmação');
    ok(await contaChats() === antes - 1, 'chat não foi apagado');
    await page.screenshot({ path: join(out, 'e3-toast-desfazer.png') });
    await page.locator('.b-toast').filter({ hasText: 'Chat apagado' }).getByRole('button', { name: 'Desfazer' }).click();
    await page.waitForTimeout(300);
    ok(await contaChats() === antes, 'Desfazer não restaurou o chat');
  } else erros.push('linha do chat não encontrada na barra lateral');

  // projeto com 3 agentes continua pedindo confirmação
  await page.locator('.pj-card').first().getByRole('button', { name: /opções/i }).click();
  await page.getByRole('menuitem', { name: 'Apagar', exact: true }).click();
  ok(await page.getByRole('dialog').getByText('Manter os agentes como avulsos').count() === 1, 'projeto com vários agentes deveria pedir confirmação');
  await page.keyboard.press('Escape');
}

// ---------- celular: paleta ----------
{
  const page = await (await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: 'dark' })).newPage();
  page.on('pageerror', (e) => erros.push(`390 pageerror: ${e.message}`));
  await page.goto(`${BASE}/projetos`);
  await page.waitForTimeout(800);
  await page.keyboard.press('Control+k');
  await page.getByRole('dialog', { name: 'Paleta de comandos' }).waitFor({ timeout: 2000 });
  await page.screenshot({ path: join(out, 'e3-paleta-390.png') });
  const largura = await page.evaluate(() => document.documentElement.scrollWidth);
  ok(largura <= 390, `rolagem horizontal no celular (${largura}px)`);
}

await browser.close();
console.log(erros.length ? `ERROS:\n${erros.join('\n')}` : 'OK sem erros');
