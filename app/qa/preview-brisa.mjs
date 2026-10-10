// QA visual da tela Projetos (Brisa): vazio, grade semeada, filtro, menu "…" e diálogos Apagar/Renomear.
// Uso: node qa/preview-brisa.mjs   (dev server em http://localhost:5173)
import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const BASE = 'http://localhost:5173';
const out = join(dirname(fileURLToPath(import.meta.url)), 'shots', 'brisa');
await mkdir(out, { recursive: true });

const PEDIDOS = [
  ['Crie uma campanha de lançamento para minha cafeteria: pesquise referências, prepare as peças e monte um calendário de posts.', 3 * 86_400_000],
  ['Faça uma pesquisa de mercado sobre academias no meu bairro, com concorrentes, preços e oportunidades.', 5 * 3_600_000],
  ['Monte uma landing page para o meu curso online: estrutura das seções, textos persuasivos e visual das telas.', 20 * 60_000],
  ['Escreva o roteiro de um vídeo de 60 segundos para o Instagram apresentando a minha loja.', 4_000],
];

const erros = [];
const browser = await chromium.launch();
for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  const tag = `${viewport.width}`;
  const page = await (await browser.newContext({ viewport, colorScheme: 'dark' })).newPage();
  page.on('pageerror', (e) => erros.push(`${tag} pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error') erros.push(`${tag} console: ${m.text()}`); });

  await page.goto(`${BASE}/projetos`);
  await page.evaluate(() => { localStorage.clear(); sessionStorage.setItem('sora.chegou', '1'); });
  await page.reload();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: join(out, `${tag}-vazio.png`), fullPage: true });

  const ids = await page.evaluate((pedidos) => {
    const s = window.__sora;
    const r = pedidos.map(([pedido, atras]) => s.criarProjeto(pedido, Date.now() - atras, { tipo: 'projeto' }).id);
    s.novoChat();
    return r;
  }, PEDIDOS);
  await page.evaluate((id) => window.__sora.aprovarProjeto?.(id), ids[0]);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: join(out, `${tag}-grade.png`), fullPage: true });

  if (viewport.width > 800) {
    await page.getByRole('button', { name: /^Prontos/ }).click();
    await page.waitForTimeout(300);
    await page.screenshot({ path: join(out, `${tag}-filtro-prontos.png`) });
    await page.getByRole('button', { name: /^Todos/ }).click();

    await page.getByPlaceholder('Buscar projetos').fill('xyz');
    await page.waitForTimeout(300);
    await page.screenshot({ path: join(out, `${tag}-busca-vazia.png`) });
    await page.getByPlaceholder('Buscar projetos').fill('');

    const menu = page.locator('.pj-card').nth(2).getByRole('button', { name: /^Opções de/ });
    await menu.focus();
    await page.keyboard.press('ArrowDown');
    await page.waitForTimeout(200);
    const focado = await page.evaluate(() => document.activeElement?.textContent);
    if (focado !== 'Abrir') erros.push(`menu: foco no 1º item esperado "Abrir", veio "${focado}"`);
    await page.screenshot({ path: join(out, `${tag}-menu.png`) });
    await page.keyboard.press('End');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(500);
    await page.screenshot({ path: join(out, `${tag}-apagar.png`) });
    await page.getByLabel('Manter os agentes como avulsos').check();
    await page.waitForTimeout(200);
    await page.screenshot({ path: join(out, `${tag}-apagar-manter.png`) });
    await page.getByRole('button', { name: 'Cancelar' }).click();

    await menu.click();
    await page.getByRole('menuitem', { name: 'Renomear' }).click();
    await page.waitForTimeout(300);
    await page.keyboard.type('Pesquisa · academias');
    await page.screenshot({ path: join(out, `${tag}-renomear.png`) });
    await page.keyboard.press('Enter');
    await page.waitForTimeout(300);
    const titulos = await page.locator('.pj-card h3').allTextContents();
    if (!titulos.includes('Pesquisa · academias')) erros.push(`renomear falhou: ${titulos.join(' | ')}`);

    // novo projeto pelo compositor → navega para /projeto/:id
    await page.getByRole('button', { name: 'Roteiro de vídeo' }).click();
    await page.getByRole('textbox', { name: /Descreva o projeto/ }).press('Enter');
    await page.waitForTimeout(400);
    await page.screenshot({ path: join(out, `${tag}-pensando.png`) });
    await page.waitForURL(/\/projeto\//, { timeout: 4000 }).catch(() => erros.push(`não navegou: ${page.url()}`));
  }
}
await browser.close();
console.log(erros.length ? `ERROS:\n${erros.join('\n')}` : 'OK sem erros');
console.log(`shots em ${out}`);
