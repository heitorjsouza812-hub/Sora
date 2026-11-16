// Botão do modelo no compositor (ícone, nome limpo, nível), Parar e lista de modelos: fotos em qa/shots/seletor2/ (conta de QA própria).
import { chromium } from '@playwright/test';
import { readFileSync, mkdirSync } from 'node:fs';
import { entrarNoContexto, BASE } from './entrar.mjs';
const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const email = `vitral13-${Date.now()}@sora.local`;
const dir = 'qa/shots/seletor2'; mkdirSync(dir, { recursive: true });
try {
  const login = await entrarNoContexto(ctx, process.env.SORA_QA_FIXA ? {} : { email });
  const headers = { Authorization: `Bearer ${login.token_acesso}` };
  const env = readFileSync('../backend/.env', 'utf8');
  const chave = env.match(/^SORA_QA_GROQ_CHAVE\s*=\s*(.+)$/m)?.[1].trim().replace(/^['"]|['"]$/g, '');
  if (chave) await ctx.request.post(`${BASE}/v1/provedores`, { headers, data: { tipo: 'groq', chave } });
  const modelos = await (await ctx.request.get(`${BASE}/v1/modelos`, { headers })).json();
  console.log('modelos', modelos.length, modelos.map(m => m.modelo).join(', ').slice(0, 400), '| principal no JSON:', 'principal' in (modelos[0] ?? {}));
  const bot = await (await ctx.request.post(`${BASE}/v1/bots/criar-por-descricao`, { headers, data: { descricao: 'Um bot que resume notícias de tecnologia' } })).json();
  console.log('bot', bot.id, bot.nome);
  // O servidor local pode não devolver raciocínio nem guardar a escolha: simulamos só essas respostas para ver o botão preenchido.
  const alvo120 = modelos.find(m => m.modelo.endsWith('gpt-oss-120b'));
  const page = await ctx.newPage();
  if (process.env.SORA_QA_SIMULAR !== '0') {
    await page.route('**/v1/modelos', async rota => {
      const lista = await (await rota.fetch()).json();
      await rota.fulfill({ json: lista.map(m => m.modelo.includes('gpt-oss') ? { ...m, raciocinio: ['baixo', 'medio', 'alto'] } : m) });
    });
    await page.route('**/v1/agentes', async rota => {
      const lista = await (await rota.fetch()).json();
      await rota.fulfill({ json: lista.map(a => a.id === bot.id ? { ...a, provedor_id: alvo120?.provedor_id, modelo: alvo120?.modelo, raciocinio: 'alto' } : a) });
    });
  }
  page.on('response', r => { if (r.request().method() === 'PATCH') console.log('PATCH', r.url().replace(BASE, ''), r.status()); });
  page.on('console', m => { if (m.type() === 'error') console.log('console:', m.text().slice(0, 200)); });
  for (const [w, h, nome] of [[1440, 900, '1440'], [390, 844, '390']]) {
    await page.setViewportSize({ width: w, height: h });
    await page.goto(`${BASE}/bots/${bot.id}`); await page.waitForTimeout(2000);
    await page.screenshot({ path: `${dir}/bot-automatico-${nome}.png` });
    await page.locator('.seletor-gatilho').click(); await page.waitForTimeout(400);
    await page.screenshot({ path: `${dir}/popover-${nome}.png` });
    const alvo = page.locator('.seletor-modelos').getByRole('button', { name: /GPT-OSS 120B/ });
    if (await alvo.count()) {
      await alvo.click(); await page.waitForTimeout(600);
      const alto = page.getByRole('button', { name: 'Alto', exact: true });
      if (await alto.count()) { await alto.click(); await page.waitForTimeout(600); }
      await page.screenshot({ path: `${dir}/popover-escolhido-${nome}.png` });
    } else console.log(nome, 'sem GPT-OSS 120B na lista');
    await page.keyboard.press('Escape'); await page.waitForTimeout(300);
    console.log(nome, 'botão:', (await page.locator('.seletor-gatilho').innerText()).replace(/\n/g, ' | '));
    await page.screenshot({ path: `${dir}/bot-escolhido-${nome}.png` });
    await page.goto(`${BASE}/configuracoes`); await page.waitForTimeout(1200);
    const sec = page.getByText('Modelos de IA').first();
    if (await sec.count()) await sec.click().catch(() => {});
    await page.waitForTimeout(500);
    const groq = page.getByRole('button', { name: /Groq/ }).first();
    if (await groq.count()) { await groq.click(); await page.waitForTimeout(600); }
    await page.screenshot({ path: `${dir}/configuracoes-modelos-${nome}.png`, fullPage: true });
  }
  // Enviar vira Parar enquanto o bot trabalha e volta a ser a seta quando termina (usa o modelo real).
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${BASE}/bots/${bot.id}`); await page.waitForTimeout(1500);
  await page.getByRole('textbox').first().fill('Escreva três parágrafos sobre a história do café.');
  await page.getByRole('button', { name: 'Enviar mensagem' }).click();
  const parar = page.getByRole('button', { name: 'Parar resposta' });
  await parar.waitFor({ timeout: 8000 }).then(async () => { console.log('Parar apareceu'); await page.screenshot({ path: `${dir}/parar-1440.png` }); }).catch(() => console.log('Parar NAO apareceu'));
  await page.getByRole('button', { name: 'Enviar mensagem' }).waitFor({ timeout: 60000 }).then(() => console.log('seta voltou')).catch(() => console.log('seta NAO voltou'));
  await page.screenshot({ path: `${dir}/depois-1440.png` });
} finally { await ctx.close(); await browser.close(); }
