// Ilha no Tauri REAL: (a) o clique ATRAVESSA a janela transparente fora da pílula e NÃO atravessa sobre ela;
// (b) o atalho global Ctrl+Shift+S abre/fecha o painel; (c) foto da área de trabalho com a ilha no topo.
// Pré-requisitos: o mesmo de qa/ilha-tauri.mjs + SORA_QA_JANELA_EXE (qa/janela-qa.cs compilado).
// Mexe no cursor do mouse (SetCursorPos) — só aponta; não clica em nada fora das janelas do QA.
import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const CDP = process.env.SORA_CDP ?? 'http://127.0.0.1:9333';
const qaDir = dirname(fileURLToPath(import.meta.url));
const shots = join(qaDir, 'shots', 'desktop-real');
await mkdir(shots, { recursive: true });
const EXE = process.env.SORA_QA_JANELA_EXE;
assert.ok(EXE, 'defina SORA_QA_JANELA_EXE');
const ps = (acao, ...args) => execFileSync('powershell', ['-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass', '-File', join(qaDir, 'janelas.ps1'), acao, ...args.map(String)],
  { encoding: 'utf8', windowsHide: true }).trim();
const espera = ms => new Promise(r => setTimeout(r, ms));
const estado = () => JSON.parse(ps('estado'));
const foto = (arquivo, x, y, w, h) => execFileSync('powershell', ['-NoProfile', '-Command', `Add-Type -AssemblyName System.Drawing,System.Windows.Forms; $b=New-Object Drawing.Bitmap ${w},${h}; $g=[Drawing.Graphics]::FromImage($b); $g.CopyFromScreen(${x},${y},0,0,$b.Size); $b.Save('${arquivo}'); $g.Dispose(); $b.Dispose()`]);
async function ate(desc, pred, ms = 6000) {
  const fim = Date.now() + ms; let u;
  while (Date.now() < fim) { u = estado(); if (pred(u)) return u; await espera(150); }
  assert.fail(`${desc}: ${JSON.stringify(u)}`);
}

const browser = await chromium.connectOverCDP(CDP);
const pags = browser.contexts().flatMap(c => c.pages());
const main = pags.find(p => !p.url().includes('janela=ilha'));
const ilha = pags.find(p => p.url().includes('janela=ilha'));
assert.ok(main && ilha, 'janelas main + ilha');
try {
  // janela de teste sob a faixa da ilha (a ilha ocupa x 560–1360, y 0–460 numa tela de 1920×1080)
  spawn(EXE, ['outra', '600', '140', '700', '300'], { detached: true, stdio: 'ignore' }).unref();
  await espera(1200);
  ps('foco-outra');
  await ate('fora de foco a ilha aparece', e => !e.principal.foco && e.ilha.visivel);
  await espera(800);
  const r = JSON.parse(ps('rect-ilha'));
  const escala = r.w / 800;
  console.log('ilha na tela:', JSON.stringify(r), 'escala', escala);
  const pilula = await ilha.evaluate(() => { const b = document.querySelector('.ilha-ancora')?.getBoundingClientRect(); return b && { x: b.x, y: b.y, w: b.width, h: b.height }; });
  assert.ok(pilula && pilula.w > 20, `pílula não achada: ${JSON.stringify(pilula)}`);
  const dentro = { x: Math.round(r.x + (pilula.x + pilula.w / 2) * escala), y: Math.round(r.y + (pilula.y + pilula.h / 2) * escala) };
  const fora = { x: r.x + 90, y: r.y + 300 }; // dentro da janela transparente, longe da pílula; sob ele há a janela do QA

  await espera(300);
  // ---- (a) clique atravessa fora da pílula ----
  ps('cursor', fora.x, fora.y); await espera(500);
  const aFora = JSON.parse(ps('janela-em', fora.x, fora.y));
  console.log('ponto fora da pílula →', JSON.stringify(aFora));
  assert.equal(aFora.ilha, false, 'fora da pílula a ilha deveria deixar o clique passar');
  assert.equal(aFora.processo, 'janela-qa', 'sob a ilha deveria estar a janela de teste do QA');
  ps('cursor', dentro.x, dentro.y); await espera(500);
  const aDentro = JSON.parse(ps('janela-em', dentro.x, dentro.y));
  console.log('ponto sobre a pílula →', JSON.stringify(aDentro));
  assert.equal(aDentro.ilha, true, 'sobre a pílula a ilha deve receber o clique');
  console.log('OK (a): clique atravessa fora da pílula e é da ilha sobre ela');
  foto(join(shots, '10-ilha-no-topo-da-tela.png'), 400, 0, 1120, 520);

  // ---- (b) atalho global ----
  ps('cursor', fora.x, fora.y); await espera(400);
  const modo = () => ilha.locator('.ilha-ancora').getAttribute('data-modo');
  const antes = await modo();
  ps('atalho-ilha'); await espera(900);
  const depois = await modo();
  foto(join(shots, '11-ilha-apos-atalho.png'), 400, 0, 1120, 520);
  ps('atalho-ilha'); await espera(900);
  const volta = await modo();
  console.log(`atalho Ctrl+Shift+S: ${antes} → ${depois} → ${volta}`);
  assert.notEqual(antes, depois, 'Ctrl+Shift+S deveria alternar o painel');
  assert.equal(volta, antes, 'segundo Ctrl+Shift+S deveria voltar ao estado anterior');
  console.log('OK (b): Ctrl+Shift+S alterna o painel da ilha');
} finally {
  ps('limpar');
  try { ps('foco-sora'); } catch { /* */ }
}
process.exit(0);
