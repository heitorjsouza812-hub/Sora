// Lince — rodada 3: repros focados de T1, T2 e L1 no navegador real (390 px).
import { readFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const BASE = 'http://localhost:5173';
const CONVITE = process.env.LINCE_CONVITE;
if (!CONVITE) throw new Error('Defina LINCE_CONVITE.');
const qa = dirname(fileURLToPath(import.meta.url));
const shots = join(qa, 'shots', 'lince', 'rodada3');
mkdirSync(shots, { recursive: true });
const fonteProvedor = readFileSync(join(qa, 'lince-provedor-falso.mjs'), 'utf8');
const CHAVE = /CHAVE_VALIDA = '([^']+)'/.exec(fonteProvedor)?.[1];
if (!CHAVE) throw new Error('Chave sintética do provedor falso não encontrada.');

const email = `lince-r3-${Date.now()}@sora.local`;
const senha = 'lince-r3-senha-forte-123';
const resultados = [];
const erros = [];
const ok = (nome, cond, extra = '') => {
  resultados.push({ nome, ok: Boolean(cond), extra });
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${nome}${extra ? ` — ${extra}` : ''}`);
};

const browser = await chromium.launch({ headless: true });
const contexto = await browser.newContext({ viewport: { width: 390, height: 844 } });
const page = await contexto.newPage();
page.on('console', mensagem => { if (mensagem.type() === 'error') erros.push(mensagem.text()); });
page.on('pageerror', erro => erros.push(`pageerror: ${erro.message}`));

try {
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.getByRole('tab', { name: 'Criar conta' }).click();
  await page.getByLabel('Nome').fill('Lince Rodada Três');
  await page.getByLabel('E-mail').fill(email);
  await page.getByLabel('Senha').fill(senha);
  await page.getByLabel('Código de convite').fill(CONVITE);
  await page.getByRole('button', { name: 'Criar conta', exact: true }).click();

  const onboarding = page.getByRole('heading', { name: /conecte sua primeira API/i });
  await onboarding.waitFor({ timeout: 15_000 });
  const sairOnboarding = page.getByRole('button', { name: 'Sair', exact: true });
  ok('T2: onboarding oferece Sair diretamente', await sairOnboarding.isVisible());
  const caixaSairOnboarding = await sairOnboarding.boundingBox();
  ok('T2: botão Sair tem alvo de toque de pelo menos 44 px', (caixaSairOnboarding?.height ?? 0) >= 44, `altura=${caixaSairOnboarding?.height ?? 0}`);
  await page.screenshot({ path: join(shots, 't2-onboarding-sair-390.png'), fullPage: true });
  await sairOnboarding.click();
  await page.getByRole('heading', { name: /Entrar na Sora/ }).waitFor({ timeout: 10_000 });
  ok('T2: Sair do onboarding encerra a sessão', true);

  await page.getByLabel('E-mail').fill(email);
  await page.getByLabel('Senha').fill(senha);
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await onboarding.waitFor({ timeout: 15_000 });

  const compativel = page.locator('article.cfg-provider-card').filter({ has: page.locator('strong', { hasText: /^Compatível com OpenAI$/ }) });
  const resumo = compativel.locator('button.cfg-provider-summary');
  if ((await resumo.getAttribute('aria-expanded')) !== 'true') await resumo.click();
  await compativel.getByLabel('URL base').fill('http://localhost:8765/v1');
  await compativel.getByLabel('Chave da API').fill(CHAVE);
  await compativel.getByRole('button', { name: 'Testar e conectar' }).click();
  await page.waitForFunction(() => !document.body.innerText.includes('conecte sua primeira API'), null, { timeout: 15_000 });

  await page.goto(`${BASE}/configuracoes`, { waitUntil: 'domcontentloaded' });
  await page.getByRole('heading', { name: /Configura/ }).first().waitFor({ timeout: 10_000 });
  const card = page.locator('article.cfg-provider-card').filter({ has: page.locator('strong', { hasText: /^Compatível com OpenAI$/ }) });
  if ((await card.locator('button.cfg-provider-summary').getAttribute('aria-expanded')) !== 'true') await card.locator('button.cfg-provider-summary').click();
  await page.waitForTimeout(300);
  const nomes = await card.locator('.cfg-model-name strong').allInnerTexts();
  const esperados = ['lince-pequeno', 'lince-medio', 'lince-grande'];
  ok('L1: cartão mostra nomes amigáveis exatos, sem prefixo técnico', esperados.every(nome => nomes.includes(nome)) && nomes.every(nome => !nome.includes('/')), nomes.join(' | '));
  const opcoes = await page.locator('.cfg-defaults option').allInnerTexts();
  ok('L1: seletores padrão não mostram openai/ nem outro prefixo técnico', opcoes.every(opcao => !/openai\//i.test(opcao)) && opcoes.some(opcao => opcao.includes('lince-medio')), opcoes.join(' | '));
  await page.screenshot({ path: join(shots, 'l1-modelos-amigaveis-390.png'), fullPage: true });

  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Abrir menu', exact: true }).click();
  const menu = page.getByRole('dialog', { name: 'Menu' });
  await menu.waitFor();
  const linkConfiguracoes = menu.getByRole('link', { name: 'Configurações' });
  const sairMenu = menu.getByRole('button', { name: 'Sair', exact: true });
  ok('T1: menu móvel mostra a identidade da conta', await menu.getByText(email, { exact: true }).isVisible());
  ok('T1: menu móvel oferece Configurações', await linkConfiguracoes.isVisible());
  ok('T1: menu móvel oferece Sair', await sairMenu.isVisible());
  const caixaSairMenu = await sairMenu.boundingBox();
  ok('T1: Sair móvel tem alvo de toque de pelo menos 44 px', (caixaSairMenu?.height ?? 0) >= 44, `altura=${caixaSairMenu?.height ?? 0}`);
  await page.screenshot({ path: join(shots, 't1-menu-conta-390.png'), fullPage: true });
  await linkConfiguracoes.click();
  await page.getByRole('heading', { name: /Configura/ }).first().waitFor({ timeout: 10_000 });
  ok('T1: Configurações do menu móvel navega para /configuracoes', new URL(page.url()).pathname === '/configuracoes', page.url());

  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Abrir menu', exact: true }).click();
  await page.getByRole('dialog', { name: 'Menu' }).getByRole('button', { name: 'Sair', exact: true }).click();
  await page.getByRole('heading', { name: /Entrar na Sora/ }).waitFor({ timeout: 10_000 });
  ok('T1: Sair do menu móvel encerra a sessão', true);
  const errosInesperados = erros.filter(erro => !/status of 401 \(Unauthorized\)/.test(erro));
  ok('console sem erros inesperados nos repros', errosInesperados.length === 0, errosInesperados.join(' || '));
  console.log('console 401 esperado ao encerrar sessão:', erros.length - errosInesperados.length);
} catch (erro) {
  ok('execução focada sem exceção', false, erro.message.split('\n')[0]);
  await page.screenshot({ path: join(shots, 'ERRO.png'), fullPage: true }).catch(() => {});
} finally {
  await browser.close();
}

const falhas = resultados.filter(resultado => !resultado.ok);
console.log(`\nRepros T1/T2/L1: ${resultados.length - falhas.length}/${resultados.length} ok`);
process.exit(falhas.length ? 1 : 0);
