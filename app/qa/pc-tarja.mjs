// Teste REAL da tarja da captura do C3 (D1): só a parte À MOSTRA de uma janela bloqueada sai preta.
// Roda contra o app de desktop aberto com a porta de depuração (ver qa/desktop-real-login.mjs) e usa o
// mesmo "worker sem modelo" de qa/pc-real.mjs (qa/pc_real_driver.py). Só mexe em janelas que ele abre:
//   - janela-qa.exe no modo "sora" (magenta, "Sora" no título → bloqueada pelo título);
//   - um Bloco de Notas com um arquivo temporário, na frente.
// Se o app estiver na tela Entrar, entra com a conta de QA e sai no fim (volta para a tela Entrar).
// Env: SORA_QA_JANELA_EXE (obrigatória), SORA_QA_API (8200), SORA_QA_DESK_EMAIL, SORA_CDP (9333).
import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { QA_SENHA } from './entrar.mjs';

const API = process.env.SORA_QA_API ?? 'http://localhost:8200';
const EMAIL = process.env.SORA_QA_DESK_EMAIL ?? 'qa-desktop-real@sora.local';
const CDP = process.env.SORA_CDP ?? 'http://127.0.0.1:9333';
const EXE = process.env.SORA_QA_JANELA_EXE;
assert.ok(EXE, 'defina SORA_QA_JANELA_EXE (qa/janela-qa.cs compilado)');
const qaDir = dirname(fileURLToPath(import.meta.url));
const backend = join(qaDir, '..', '..', 'backend');
const shots = join(qaDir, 'shots', 'desktop-real');
await mkdir(shots, { recursive: true });
const espera = ms => new Promise(r => setTimeout(r, ms));

async function api(caminho, { token, method = 'GET', body } = {}) {
  const r = await fetch(`${API}${caminho}`, { method, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: body ? JSON.stringify(body) : undefined });
  const t = await r.text();
  return { status: r.status, corpo: t ? JSON.parse(t) : null };
}
const ps = (acao, ...args) => execFileSync('powershell', ['-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass', '-File', join(qaDir, 'janelas.ps1'), acao, ...args.map(String)], { encoding: 'utf8', windowsHide: true }).trim();

function motorista(...args) {
  return new Promise((resolve, reject) => {
    const filho = spawn('uv', ['run', 'python', join(qaDir, 'pc_real_driver.py'), ...args], { cwd: backend, env: { ...process.env, PYTHONPATH: '.', PYTHONIOENCODING: 'utf-8' } });
    let saida = '';
    filho.stdout.on('data', d => { saida += d; });
    filho.stderr.on('data', d => { saida += d; });
    filho.on('close', () => {
      const l = saida.split(/\r?\n/).find(x => x.startsWith('RESULTADO '));
      if (l) resolve(JSON.parse(l.slice(10))); else reject(new Error(`motorista sem resultado:\n${saida.slice(-1500)}`));
    });
  });
}

/** Conta pixels num retângulo da captura [x1,y1,x2,y2): pretos (0,0,0), magenta e o resto. */
function contar(png, r) {
  const script = `Add-Type -AssemblyName System.Drawing; $b=[Drawing.Bitmap]::FromFile('${png}');
$p=0;$m=0;$o=0; $x2=[Math]::Min(${r[2]},$b.Width); $y2=[Math]::Min(${r[3]},$b.Height)
for($y=[Math]::Max(${r[1]},0);$y -lt $y2;$y+=2){for($x=[Math]::Max(${r[0]},0);$x -lt $x2;$x+=2){$c=$b.GetPixel($x,$y)
if($c.R -eq 0 -and $c.G -eq 0 -and $c.B -eq 0){$p++}elseif($c.R -gt 200 -and $c.G -lt 60 -and $c.B -gt 200){$m++}else{$o++}}}
$w=$b.Width; $b.Dispose(); "{""pretos"":$p,""magenta"":$m,""outros"":$o,""largura"":$w}"`;
  return JSON.parse(execFileSync('powershell', ['-NoProfile', '-Command', script], { encoding: 'utf8' }).trim().split(/\r?\n/).pop());
}
const fracao = c => c.pretos / Math.max(1, c.pretos + c.magenta + c.outros);

// ---- conta de QA no app (nunca a do Heitor) ----
const browser = await chromium.connectOverCDP(CDP);
const main = browser.contexts().flatMap(c => c.pages()).find(p => !p.url().includes('janela=ilha'));
assert.ok(main, 'janela principal não encontrada pela porta de depuração');
await main.locator('.shell-account, input[type="password"]').first().waitFor({ state: 'attached', timeout: 25_000 });
let entrei = false;
if (await main.getByLabel('E-mail').count()) {
  await main.getByLabel('E-mail').fill(EMAIL);
  await main.getByLabel('Senha').fill(QA_SENHA);
  await main.getByRole('button', { name: 'Entrar', exact: true }).click();
  await main.locator('.account-logout').waitFor({ state: 'attached', timeout: 20_000 });
  entrei = true;
}
const conta = await main.locator('.shell-account').innerText().catch(() => '');
assert.ok(!/heitor/i.test(conta), `o app está numa conta que não é de QA: ${conta}`);
console.log('app na conta de QA:', JSON.stringify(conta.replace(/\s+/g, ' ')), entrei ? '(entrei agora)' : '');

const entrada = await api('/v1/auth/entrar', { method: 'POST', body: { email: EMAIL, senha: QA_SENHA } });
assert.equal(entrada.status, 200, 'login de QA na API');
const token = entrada.corpo.token_acesso;
const usuario = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString()).sub;
const bot = process.env.SORA_QA_BOT ?? (await api('/v1/agentes', { token })).corpo.find(b => b.nome === 'Piloto do PC')?.id;
assert.ok(bot, 'bot de QA "Piloto do PC" (rode qa/pc-tauri.mjs antes)');

async function observar(nome) {
  const png = join(shots, nome);
  for (let tentativa = 1; ; tentativa++) {
    const r = await motorista('observar', usuario, bot, png);
    if (r.ok || tentativa >= 6) return { ...r, png };
    console.log(`observar falhou (${tentativa}): ${r.erro}; tentando de novo`);
    await espera(3000);
  }
}

// ---- janelas do QA ----
const arquivo = join(tmpdir(), `qa-tarja-${Date.now()}.txt`);
await writeFile(arquivo, 'Bloco de Notas do QA da tarja (D1). Pode fechar.\r\n');
const nomeArquivo = arquivo.split(/[\\/]/).pop();
const resultado = {};
// coordenadas físicas (tela 1920x1080 a 100 %); a captura sai em 1280 px (escala 1,5)
const MAGENTA = [100, 150, 1000, 650]; // x, y, largura, altura
const NOTAS = [600, 400, 900, 550];
const cap = ([x, y, w, h]) => [x, y, x + w, y + h].map(v => Math.round(v / 1.5));
try {
  ps('limpar');
  spawn(EXE, ['sora', ...MAGENTA.map(String)], { detached: true, stdio: 'ignore' }).unref();
  await espera(1500);
  spawn('notepad.exe', [arquivo], { detached: true, stdio: 'ignore' }).unref();
  let pronto = false;
  for (let i = 0; i < 30 && !pronto; i++) { await espera(400); try { ps('posicionar-titulo', nomeArquivo, ...NOTAS); pronto = true; } catch { /* abrindo */ } }
  assert.ok(pronto, 'o Bloco de Notas do QA não abriu');
  await espera(600);
  ps('foco-titulo', nomeArquivo);
  await espera(900);

  // 1) PARCIALMENTE coberta: só o "L" à mostra da janela magenta sai preto; o Bloco de Notas aparece
  const o1 = await observar('60-tarja-parcial.png');
  assert.ok(o1.ok, `observar: ${o1.erro}`);
  assert.ok(!o1.arvore.some(e => e.papel === 'aviso'), 'a captura não deveria ser omitida com o Bloco de Notas na frente');
  const [mx1, my1, , my2] = cap(MAGENTA);
  const [nx1, ny1, nx2, ny2] = cap(NOTAS);
  const tela1 = contar(o1.png, [0, 0, 4000, 4000]);
  const visivel = contar(o1.png, [mx1 + 4, my1 + 4, nx1 - 4, my2 - 4]); // faixa da magenta à esquerda do Bloco de Notas
  const notas = contar(o1.png, [nx1 + 12, ny1 + 12, nx2 - 12, ny2 - 12]);
  resultado.parcial = { tela: tela1, visivel, notas, pretoNaTela: fracao(tela1).toFixed(3) };
  console.log('1) parcial →', JSON.stringify(resultado.parcial));
  assert.equal(tela1.magenta, 0, 'nenhum pixel magenta (da janela "Sora") pode sair na captura');
  assert.ok(fracao(visivel) > 0.99, 'a parte à mostra da janela "Sora" deveria sair preta');
  assert.ok(fracao(notas) < 0.2, 'o Bloco de Notas deveria aparecer (não preto)');

  // 2) TOTALMENTE coberta: a magenta fica atrás do Bloco de Notas, dentro dele → nada tarjado ali
  ps('posicionar-titulo', 'Sora - QA da tarja', 700, 500, 600, 300);
  ps('foco-titulo', nomeArquivo);
  await espera(900);
  const o2 = await observar('61-tarja-coberta.png');
  assert.ok(o2.ok, `observar: ${o2.erro}`);
  const atras = contar(o2.png, cap([700, 500, 600, 300]));
  const tela2 = contar(o2.png, [0, 0, 4000, 4000]);
  resultado.coberta = { atras, tela: tela2 };
  console.log('2) coberta →', JSON.stringify(resultado.coberta));
  assert.equal(tela2.magenta, 0, 'nenhum pixel magenta');
  assert.ok(fracao(atras) < 0.05, 'janela bloqueada totalmente coberta não deveria ser tarjada');

  // 3) bloqueada POR CIMA e em primeiro plano: a captura é omitida (regra antiga, mantida)
  ps('foco-titulo', 'Sora - QA da tarja');
  await espera(900);
  const o3 = await observar('62-tarja-bloqueada-na-frente.png');
  const aviso = (o3.arvore ?? []).find(e => e.papel === 'aviso');
  resultado.naFrente = { omitida: Boolean(aviso), aviso: aviso?.nome?.slice(0, 120) };
  console.log('3) bloqueada na frente →', JSON.stringify(resultado.naFrente));
  assert.ok(aviso, 'com a janela "Sora" em primeiro plano a captura deveria ser omitida');
  assert.equal(contar(o3.png, [0, 0, 4000, 4000]).magenta, 0, 'nenhum pixel magenta');
  // 4) ILHA à mostra (app fora de foco) sobre uma janela comum: só a pílula sai preta, o resto da
  //    janela da ilha (800×460, transparente) deixa ver o que está atrás.
  ps('limpar');
  await espera(600);
  const ILHA = [560, 0, 800, 460];
  spawn(EXE, ['outra', ...ILHA.map(String)], { detached: true, stdio: 'ignore' }).unref();
  await espera(1500);
  let ilhaVisivel = false;
  for (let i = 0; i < 20 && !ilhaVisivel; i++) { ilhaVisivel = JSON.parse(ps('estado')).ilha.visivel; if (!ilhaVisivel) await espera(400); }
  assert.ok(ilhaVisivel, 'a ilha deveria estar à mostra com o app fora de foco');
  await espera(1200);
  const o4 = await observar('63-tarja-ilha.png');
  assert.ok(o4.ok, `observar: ${o4.erro}`);
  const [ix1, iy1, ix2, iy2] = cap(ILHA);
  const janelaIlha = contar(o4.png, [ix1 + 2, iy1 + 2, ix2 - 2, iy2 - 2]);
  // faixa transparente da ilha logo abaixo da pílula (sem a borda da janela de teste nem o Bloco de Notas)
  const metadeDeBaixo = contar(o4.png, [ix1 + 40, iy1 + Math.round((iy2 - iy1) * 0.25), ix2 - 40, iy1 + Math.round((iy2 - iy1) * 0.5)]);
  resultado.ilha = { janelaIlha, metadeDeBaixo, pretoNaJanela: fracao(janelaIlha).toFixed(3) };
  console.log('4) ilha →', JSON.stringify(resultado.ilha));
  assert.ok(janelaIlha.pretos > 0, 'a pílula da ilha deveria sair preta');
  assert.ok(fracao(janelaIlha) < 0.3, 'só a pílula pode sair preta, não a janela inteira da ilha');
  assert.equal(metadeDeBaixo.pretos, 0, 'a faixa transparente da janela da ilha não pode sair preta');
  console.log('RESUMO', JSON.stringify(resultado));
} finally {
  try { ps('fechar-suave', nomeArquivo); } catch { /* já fechado */ }
  ps('limpar');
  await espera(1200);
  try { ps('fechar-titulo', nomeArquivo); } catch { /* já fechado */ }
  await rm(arquivo, { force: true });
  if (entrei && (await main.locator('.account-logout').count())) {
    await main.evaluate(() => document.querySelector('.account-logout')?.click());
    await main.getByLabel('E-mail').waitFor({ timeout: 15_000 }).catch(() => {});
    console.log('saí da conta de QA: app de volta na tela Entrar');
  }
}
process.exit(0);
