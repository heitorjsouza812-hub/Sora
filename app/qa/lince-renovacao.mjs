// Lince — renovação silenciosa depois de recarregar (web). Roda por último na rodada (Âncora mexeu na tolerância de 15 s).
import { chromium } from '@playwright/test';
import { entrarNoContexto, BASE } from './entrar.mjs';

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext();
await entrarNoContexto(ctx);
const reqs = [];
const logada = async (p) => { await p.waitForLoadState('networkidle'); await p.waitForTimeout(600); return !(await p.locator('h1').first().innerText().catch(() => '')).includes('Entrar na Sora'); };
const novaPagina = async () => { const p = await ctx.newPage(); p.on('response', r => { if (r.url().includes('/auth/renovar')) reqs.push(`${new Date().toISOString().slice(14, 23)} ${r.status()}`); }); return p; };
const resultados = [];
const reg = (nome, ok, extra = '') => { resultados.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${nome}${extra ? ' — ' + extra : ''}`); };

const p = await novaPagina();
await p.goto(BASE, { waitUntil: 'domcontentloaded' });
reg('abre já logada (cookie de renovação)', await logada(p));
const antes = reqs.length;
console.log('chamadas /renovar na 1ª abertura:', antes);
for (let i = 1; i <= 4; i++) { await p.reload({ waitUntil: 'domcontentloaded' }); reg(`recarregar #${i} continua logada`, await logada(p)); }
console.log('/renovar até aqui:', reqs.join(' | '));

// navegação direta a uma rota profunda
await p.goto(`${BASE}/configuracoes`, { waitUntil: 'domcontentloaded' });
reg('/configuracoes direto, logada', await logada(p));

// 15+ s depois (fora da janela de tolerância)
console.log('esperando 17 s…'); await p.waitForTimeout(17000);
await p.reload({ waitUntil: 'domcontentloaded' });
reg('recarregar depois de 17 s continua logada', await logada(p));

// duas abas ao mesmo tempo
const a = await novaPagina(), b = await novaPagina();
await Promise.all([a.goto(BASE, { waitUntil: 'domcontentloaded' }), b.goto(BASE, { waitUntil: 'domcontentloaded' })]);
reg('duas abas abrindo juntas: A logada', await logada(a));
reg('duas abas abrindo juntas: B logada', await logada(b));
console.log('esperando 17 s…'); await a.waitForTimeout(17000);
await a.reload({ waitUntil: 'domcontentloaded' });
reg('aba A recarrega 17 s depois (corrida das duas abas)', await logada(a));
await b.reload({ waitUntil: 'domcontentloaded' });
reg('aba B recarrega 17 s depois (corrida das duas abas)', await logada(b));
console.log('/renovar total:', reqs.join(' | '));
await browser.close();
process.exit(resultados.every(Boolean) ? 0 : 1);
