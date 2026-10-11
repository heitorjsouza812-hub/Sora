// Item 57 · auditoria de contraste (WCAG 2.1 AA) de todos os textos visíveis.
// Uso: node qa/contraste.mjs [rotas…] [--todos] [--json]
//  - percorre as rotas em 1440 e 390 px (dev server em http://localhost:5173);
//  - para cada nó de texto visível mede a cor efetiva (opacidade dos ancestrais incluída) contra o
//    fundo composto (camadas rgba até um fundo opaco) e compara com 4,5:1 (ou 3:1 em texto grande);
//  - texto sobre imagem/gradiente/canvas fica como "não medido";
//  - escreve qa/contraste.md e sai com código 1 se algo falhar.
import { chromium } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const BASE_URL = 'http://localhost:5173';
const qaDir = dirname(fileURLToPath(import.meta.url));
const ROTAS = ['/', '/projetos', '/agentes', '/agentes/novo', '/projeto/@projeto', '/chat/@1', '/chat/@2', '/revisao/@projeto', '/configuracoes', '/configuracoes#provedor', '/configuracoes#conta', '/configuracoes#modal', '/agentes/novo#configurar', '/projeto/@projeto#menu', '/plugins', '/celular'];
const VIEWPORTS = [{ width: 1440, height: 900 }, { width: 390, height: 844 }];
const PEDIDO = 'Crie uma campanha para lançar minha cafeteria: pesquise referências, prepare as peças e monte um calendário de posts.';

const args = process.argv.slice(2);
const todos = args.includes('--todos');
const rotas = args.filter(a => a.startsWith('/'));

async function semear(page) {
  await page.goto(BASE_URL + '/', { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => { localStorage.clear(); sessionStorage.setItem('sora.chegou', '1'); });
  await page.goto(BASE_URL + '/', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => Boolean(window.__sora), null, { timeout: 10_000 });
  return page.evaluate((m) => { const p = window.__sora.criarProjeto(m, Date.now() - 120_000); return { id: p.id, agentes: p.agenteIds }; }, PEDIDO);
}

const resolver = (rota, s) => rota.replace('@projeto', s.id).replace(/@(\d+)/g, (_, n) => s.agentes[Number(n) - 1] ?? 'sora');

// roda no navegador: mede cada texto visível
function medirNaPagina() {
  const parse = (txt) => {
    if (!txt || txt === 'transparent') return [0, 0, 0, 0];
    let m = txt.match(/rgba?\(([^)]+)\)/);
    if (m) { const p = m[1].split(/[\s,/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p[3] ?? 1]; }
    m = txt.match(/color\(srgb ([^)]+)\)/);
    if (m) { const p = m[1].split(/[\s/]+/).filter(Boolean).map(Number); return [p[0] * 255, p[1] * 255, p[2] * 255, p[3] ?? 1]; }
    return null;
  };
  const sobre = (cima, baixo) => { const a = cima[3]; return [0, 1, 2].map(i => cima[i] * a + baixo[i] * (1 - a)).concat(1); };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const razao = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const hex = (c) => '#' + c.slice(0, 3).map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
  const seletor = (el) => {
    const partes = [];
    for (let e = el; e && e !== document.body && partes.length < 4; e = e.parentElement) {
      const cls = [...e.classList].filter(c => !/^_|^\d/.test(c)).slice(0, 2).join('.');
      partes.unshift(e.tagName.toLowerCase() + (cls ? '.' + cls : ''));
    }
    return partes.join(' > ');
  };
  const fundoDe = (el) => {
    const camadas = [];
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage !== 'none' && !/^url\(.*\.svg/.test(cs.backgroundImage)) {
        // gradiente radial leve do .app-shell é decorativo: usa a cor base dele
        if (!e.classList.contains('app-shell')) return { imagem: true };
      }
      if (e.tagName === 'IMG' || e.tagName === 'CANVAS' || e.tagName === 'VIDEO') return { imagem: true };
      const c = parse(cs.backgroundColor);
      if (c && c[3] > 0) { camadas.push(c); if (c[3] >= 1) break; }
    }
    let base = [5, 6, 8, 1]; // --surface-1
    for (let i = camadas.length - 1; i >= 0; i--) base = sobre(camadas[i], base);
    return { cor: base };
  };
  const vistos = new Set();
  const out = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const texto = n.textContent.replace(/\s+/g, ' ').trim();
    if (!texto) continue;
    const el = n.parentElement;
    if (!el || vistos.has(el)) continue;
    vistos.add(el);
    const cs = getComputedStyle(el);
    if (cs.visibility !== 'visible' || cs.display === 'none') continue;
    const r = document.createRange(); r.selectNodeContents(n);
    const box = r.getBoundingClientRect();
    if (box.width < 1 || box.height < 1 || box.bottom < 0 || box.top > innerHeight || box.right < 0 || box.left > innerWidth) continue;
    if (el.closest('[aria-hidden="true"] svg, .b-sr, .sr-only') || cs.clip === 'rect(0px, 0px, 0px, 0px)') continue;
    // opacidade acumulada; elementos quase invisíveis (animação de entrada) ficam de fora
    let op = 1;
    for (let e = el; e; e = e.parentElement) op *= Number(getComputedStyle(e).opacity);
    if (op < 0.05) continue;
    const cor = parse(cs.color);
    if (!cor) continue;
    const tam = parseFloat(cs.fontSize);
    const peso = Number(cs.fontWeight) || 400;
    const grande = tam >= 24 || (tam >= 18.66 && peso >= 700);
    const minimo = grande ? 3 : 4.5;
    const desabilitado = Boolean(el.closest(':disabled, [aria-disabled="true"]'));
    const f = fundoDe(el);
    const item = { texto: texto.slice(0, 48), seletor: seletor(el), tam, peso, minimo, desabilitado };
    if (f.imagem) { out.push({ ...item, naoMedido: true }); continue; }
    const efetiva = sobre([cor[0], cor[1], cor[2], cor[3] * op], f.cor);
    out.push({ ...item, cor: hex(efetiva), fundo: hex(f.cor), razao: Math.round(razao(efetiva, f.cor) * 100) / 100 });
  }
  return out;
}

async function prepararEstado(page, rota) {
  if (rota.endsWith('#provedor')) await page.getByRole('button', { name: /OpenAI/i }).first().click().catch(() => {});
  if (rota.endsWith('#conta') || rota.endsWith('#modal')) await page.getByRole('tab', { name: 'Conta' }).click().catch(() => {});
  if (rota.endsWith('#modal')) await page.getByRole('button', { name: 'Apagar todos os dados' }).click().catch(() => {});
  if (rota.endsWith('#configurar')) await page.getByRole('tab', { name: 'Configurar', exact: true }).click().catch(() => {});
  if (rota.endsWith('#menu')) await page.getByRole('button', { name: /^Opções de/ }).first().click().catch(() => {});
}

const browser = await chromium.launch();
const linhas = [];
let totalMedidos = 0, totalNaoMedidos = 0;
try {
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: vp, colorScheme: 'dark', reducedMotion: 'reduce' });
    const page = await ctx.newPage();
    const seed = await semear(page);
    for (const rota of rotas.length ? rotas : ROTAS) {
      await page.goto(BASE_URL + resolver(rota.replace(/#.*/, ''), seed), { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(1500);
      await prepararEstado(page, rota);
      await page.waitForTimeout(400);
      const itens = await page.evaluate(medirNaPagina);
      for (const it of itens) {
        if (it.naoMedido) { totalNaoMedidos++; continue; }
        totalMedidos++;
        if (it.desabilitado) continue; // WCAG 1.4.3 isenta controles desativados
        if (it.razao < it.minimo || todos) linhas.push({ vp: `${vp.width}`, rota, ...it });
      }
    }
    await ctx.close();
  }
} finally {
  await browser.close();
}

const falhas = linhas.filter(l => l.razao < l.minimo);
const pequenas = falhas.filter(l => l.tam <= 13);
const md = [
  '# Contraste dos textos (WCAG 2.1 AA)',
  '',
  `Gerado por \`node qa/contraste.mjs\` em ${new Date().toISOString().slice(0, 16).replace('T', ' ')}.`,
  `Rotas: ${(rotas.length ? rotas : ROTAS).join(' · ')} — em 1440 e 390 px.`,
  '',
  `- Textos medidos: **${totalMedidos}** (sobre imagem/gradiente, não medidos: ${totalNaoMedidos})`,
  `- Falhas: **${falhas.length}** (das quais ${pequenas.length} em 11–13 px)`,
  '- Mínimo: 4,5:1 (texto normal) · 3:1 (≥ 24 px, ou ≥ 18,66 px em negrito). Controles desativados são isentos.',
  '',
  falhas.length ? '| px | Rota | Texto | Elemento | Tam. | Cor / fundo | Razão |\n|---|---|---|---|---|---|---|' : 'Nenhuma falha. ✅',
  ...falhas.map(l => `| ${l.vp} | \`${l.rota}\` | ${l.texto.replace(/\|/g, '\\|')} | \`${l.seletor}\` | ${l.tam}px/${l.peso} | ${l.cor} / ${l.fundo} | **${l.razao}** (mín. ${l.minimo}) |`),
  '',
].join('\n');
await writeFile(join(qaDir, 'contraste.md'), md, 'utf8');
if (args.includes('--json')) console.log(JSON.stringify(linhas, null, 2));
console.log(`contraste: ${totalMedidos} textos medidos, ${falhas.length} falhas → qa/contraste.md`);
process.exitCode = falhas.length ? 1 : 0;
