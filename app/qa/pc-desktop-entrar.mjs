// Vela-12: entra (ou sai) com a conta de QA no app de desktop aberto com a porta de depuração 9333.
//   node qa/pc-desktop-entrar.mjs entrar   → sai da conta atual e entra com SORA_QA_DESK_EMAIL
//   node qa/pc-desktop-entrar.mjs sair     → sai e deixa o app na tela Entrar
import { chromium } from '@playwright/test';
import { QA_SENHA } from './entrar.mjs';

const CDP = process.env.SORA_CDP ?? 'http://127.0.0.1:9333';
const EMAIL = process.env.SORA_QA_DESK_EMAIL ?? 'qa-desktop-real@sora.local';
const fase = process.argv[2] ?? 'entrar';
const b = await chromium.connectOverCDP(CDP);
const main = b.contexts().flatMap(c => c.pages()).find(p => !p.url().includes('janela=ilha'));
await main.evaluate(() => sessionStorage.setItem('sora.onboarding-pulado.v1', '1'));
await main.locator('.account-logout, input[type="password"]').first().waitFor({ state: 'attached', timeout: 25_000 });
if (await main.locator('.account-logout').count()) await main.evaluate(() => document.querySelector('.account-logout')?.click());
await main.getByLabel('E-mail').waitFor({ timeout: 15_000 });
if (fase === 'sair') { console.log('OK: tela Entrar'); process.exit(0); }
await main.getByLabel('E-mail').fill(EMAIL);
await main.getByLabel('Senha').fill(QA_SENHA);
await main.getByRole('button', { name: 'Entrar', exact: true }).click();
await main.locator('.account-logout').waitFor({ state: 'attached', timeout: 20_000 });
console.log('OK: logado como', EMAIL);
process.exit(0);
