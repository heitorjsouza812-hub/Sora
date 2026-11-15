// Teste REAL do controle do PC (C3) + aviso fora de foco, no Tauri de verdade, sem depender de modelo.
// O "bot" é o ComputadorPcUsuario do backend (qa/pc_real_driver.py); o "usuário" é este script (API + CDP).
// Cenários:  node qa/pc-real.mjs notepad   → cartão da 1ª ação, aviso fora de foco, ilha, digitar, borda, Parar
//            node qa/pc-real.mjs senha     → campo de senha recusado (janela-qa.exe senha)
//            node qa/pc-real.mjs bloqueado → cmd/painel de controle recusados
// Env: SORA_QA_API (8200), SORA_QA_JANELA_EXE, SORA_QA_DESK_EMAIL, SORA_QA_BOT, SORA_QA_USUARIO, SORA_QA_NOTEPAD_ARQ
import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { QA_SENHA } from './entrar.mjs';

const API = process.env.SORA_QA_API ?? 'http://localhost:8200';
const EMAIL = process.env.SORA_QA_DESK_EMAIL ?? 'qa-desktop-real@sora.local';
const CDP = process.env.SORA_CDP ?? 'http://127.0.0.1:9333';
const qaDir = dirname(fileURLToPath(import.meta.url));
const backend = join(qaDir, '..', '..', 'backend');
const shots = join(qaDir, 'shots', 'desktop-real');
const tmp = process.env.SORA_QA_TMP ?? shots;
await mkdir(shots, { recursive: true });
const espera = ms => new Promise(r => setTimeout(r, ms));

async function api(caminho, { token, method = 'GET', body } = {}) {
  const r = await fetch(`${API}${caminho}`, { method, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: body ? JSON.stringify(body) : undefined });
  const t = await r.text();
  return { status: r.status, corpo: t ? JSON.parse(t) : null };
}
const entrada = await api('/v1/auth/entrar', { method: 'POST', body: { email: EMAIL, senha: QA_SENHA } });
assert.equal(entrada.status, 200, 'login de QA');
const token = entrada.corpo.token_acesso;
const usuario = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString()).sub;
const bot = process.env.SORA_QA_BOT ?? (await api('/v1/agentes', { token })).corpo.find(b => b.nome === 'Piloto do PC')?.id;
assert.ok(bot, 'bot de QA "Piloto do PC" (rode qa/pc-tauri.mjs antes)');

const ps = (acao, ...args) => execFileSync('powershell', ['-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass', '-File', join(qaDir, 'janelas.ps1'), acao, ...args.map(String)], { encoding: 'utf8', windowsHide: true }).trim();
const tela = arquivo => execFileSync('powershell', ['-NoProfile', '-Command', `Add-Type -AssemblyName System.Drawing,System.Windows.Forms; $b=New-Object Drawing.Bitmap 1920,1080; $g=[Drawing.Graphics]::FromImage($b); $g.CopyFromScreen(0,0,0,0,$b.Size); $b.Save('${arquivo}')`]);

/** Roda o motorista (papel do worker) e devolve o JSON da linha RESULTADO. */
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
const observar = png => motorista('observar', usuario, bot, png);
const agir = (acao, espera_s = 40) => motorista('agir', usuario, bot, JSON.stringify(acao), espera_s);
async function esperarCartao(filtro, ms = 25_000) {
  const fim = Date.now() + ms;
  while (Date.now() < fim) {
    const p = (await api('/v1/atencao', { token })).corpo.find(filtro);
    if (p) return p;
    await espera(400);
  }
  return null;
}
const decidir = (id, decisao) => api(`/v1/aprovacoes/${id}/decidir`, { method: 'POST', token, body: { decisao } });

const cenario = process.argv[2] ?? 'notepad';
const browser = await chromium.connectOverCDP(CDP);
const pags = browser.contexts().flatMap(c => c.pages());
const main = pags.find(p => !p.url().includes('janela=ilha'));
const ilha = pags.find(p => p.url().includes('janela=ilha'));
const resultado = {};

if (cenario === 'notepad') {
  // Bloco de Notas já aberto pelo QA com um arquivo temporário; vira o programa em foco (a Sora fica fora de foco).
  ps('foco-processo', 'notepad');
  await espera(800);
  const base = (await api('/v1/atencao', { token })).corpo.length;
  console.log('pedidos pendentes antes:', base, '| título da Sora:', JSON.stringify(await main.title()));
  const execucao = agir({ tipo: 'digitar', texto: 'Lista de compras: cafe, pao, leite', janela_programa: 'notepad.exe' }, 120);
  const cartao = await esperarCartao(p => p.titulo === 'Usar um programa do seu computador');
  assert.ok(cartao, 'a primeira ação no Bloco de Notas deveria abrir o cartão "Usar um programa do seu computador"');
  resultado.cartao = { titulo: cartao.titulo, resumo: cartao.resumo, opcoes: cartao.opcoes };
  console.log('OK cartão de 1ª ação:', JSON.stringify(resultado.cartao));
  // aviso fora de foco: título "(N) Sora" e a notificação do sistema (foto da tela logo depois do cartão)
  await espera(1200);
  tela(join(shots, '30-aviso-fora-de-foco-toast.png'));
  const titulo = await main.title();
  const estadoJanelas = JSON.parse(ps('estado'));
  console.log('título da Sora com o pedido:', JSON.stringify(titulo), '| janelas:', JSON.stringify(estadoJanelas));
  resultado.titulo = titulo;
  resultado.ilhaVisivel = estadoJanelas.ilha.visivel;
  await espera(500);
  if (estadoJanelas.ilha.visivel) {
    await ilha.screenshot({ path: join(shots, '31-ilha-com-cartao-do-pc.png') });
    resultado.ilhaTexto = (await ilha.locator('body').innerText().catch(() => '')).replace(/\s+/g, ' ').slice(0, 300);
    console.log('ilha mostra:', JSON.stringify(resultado.ilhaTexto));
  }
  // decide pela ilha (clicando no botão "Permitir uma vez", como o usuário)
  let decidiuPelaIlha = false;
  if (estadoJanelas.ilha.visivel) {
    const botao = ilha.getByRole('button', { name: /Permitir uma vez/i }).first();
    if (await botao.count()) { await botao.click(); decidiuPelaIlha = true; }
  }
  if (!decidiuPelaIlha) console.log('AVISO: não achei "Permitir uma vez" na ilha; decidindo pela API');
  if (!decidiuPelaIlha) assert.equal((await decidir(cartao.id, 'permitir')).status, 204);
  resultado.decidiuPelaIlha = decidiuPelaIlha;
  const r = await execucao;
  console.log('resultado da ação:', JSON.stringify(r));
  assert.equal(r.ok, true, `digitar no Bloco de Notas deveria dar certo: ${JSON.stringify(r)}`);
  // borda acesa e botão Parar (janelas nativas da ponte) enquanto o bot tem a vez
  await espera(500);
  const nativas = JSON.parse(ps('listar-sora')).filter(j => /SoraPc/.test(j.classe));
  resultado.nativas = nativas;
  console.log('janelas nativas da borda/Parar:', JSON.stringify(nativas));
  tela(join(shots, '32-borda-e-parar.png'));
  assert.ok(nativas.some(j => j.classe === 'SoraPcBorda' && j.visivel), 'borda acesa visível');
  assert.ok(nativas.some(j => j.classe === 'SoraPcParar' && j.visivel), 'botão Parar visível');
  // conferir o texto no Bloco de Notas pela árvore de acessibilidade
  const obs = await observar(join(tmp, 'obs-depois-de-digitar.png'));
  const doc = obs.arvore.find(e => e.papel === 'documento');
  console.log('árvore depois de digitar → documento:', JSON.stringify(doc), '| contador:', JSON.stringify(obs.arvore.find(e => /caractere/.test(e.nome ?? ''))));
  resultado.documento = doc;
  resultado.contador = obs.arvore.find(e => /caractere/.test(e.nome ?? ''))?.nome;
  // segunda ação no MESMO programa não pede de novo (Permitir uma vez vale 5 min)
  const r2 = await agir({ tipo: 'tecla', tecla: 'ctrl+s' }, 20);
  console.log('ctrl+s (2ª ação, sem novo cartão):', JSON.stringify(r2));
  resultado.segundaAcao = r2;
  const sobrou = (await api('/v1/atencao', { token })).corpo.filter(p => p.titulo === 'Usar um programa do seu computador');
  assert.equal(sobrou.length, 0, 'a 2ª ação no mesmo programa não deveria abrir outro cartão');
  console.log('RESUMO', JSON.stringify(resultado));
}

if (cenario === 'senha') {
  // janela nossa (janela-qa.exe) com um campo de SENHA em foco e um campo comum
  const exe = process.env.SORA_QA_JANELA_EXE;
  assert.ok(exe, 'defina SORA_QA_JANELA_EXE');
  ps('limpar');
  spawn(exe, ['senha', '140', '140'], { detached: true, stdio: 'ignore' }).unref();
  await espera(1500);
  ps('foco-processo', 'janela-qa');
  await espera(600);
  const obs = await observar(join(tmp, 'obs-senha.png'));
  const campoSenha = obs.arvore.filter(e => (e.estados ?? []).includes('senha') || /senha/i.test(e.nome ?? ''));
  console.log('árvore: elementos com "senha":', JSON.stringify(campoSenha));
  console.log('janela ativa:', JSON.stringify(obs.janelas.find(j => j.ativa)));
  // 1ª ação no programa: cartão; Permitir uma vez
  const execucao = agir({ tipo: 'digitar', texto: 'segredo-do-teste', janela_programa: 'janela-qa.exe' }, 90);
  const cartao = await esperarCartao(p => p.titulo === 'Usar um programa do seu computador');
  assert.ok(cartao, 'cartão da 1ª ação em janela-qa.exe');
  console.log('cartão:', cartao.resumo.slice(0, 120));
  assert.equal((await decidir(cartao.id, 'permitir')).status, 204);
  const r = await execucao;
  console.log('digitar no campo de SENHA →', JSON.stringify(r));
  resultado.senha = r;
  assert.equal(r.ok, false, 'digitar em campo de senha deveria ser recusado');
  assert.match(r.erro, /senha/i, `a recusa deveria falar de senha: ${r.erro}`);
  // o campo de senha continua vazio; Tab leva ao campo comum, onde digitar funciona
  const antes = await observar(join(tmp, 'obs-senha-2.png'));
  console.log('árvore depois da recusa (campos):', JSON.stringify(antes.arvore.filter(e => /campo|senha/i.test(`${e.nome} ${e.papel}`))));
  const tab = await agir({ tipo: 'tecla', tecla: 'Tab', janela_programa: 'janela-qa.exe' }, 20);
  const comum = await agir({ tipo: 'digitar', texto: 'texto comum ok', janela_programa: 'janela-qa.exe' }, 20);
  console.log('Tab →', JSON.stringify(tab), '| digitar no campo comum →', JSON.stringify(comum));
  resultado.tab = tab; resultado.comum = comum;
  const depois = await observar(join(tmp, 'obs-senha-3.png'));
  const valores = depois.arvore.filter(e => e.valor).map(e => ({ nome: e.nome, valor: e.valor, estados: e.estados }));
  console.log('valores visíveis na árvore:', JSON.stringify(valores));
  resultado.valores = valores;
  ps('limpar');
  console.log('RESUMO', JSON.stringify(resultado));
}

if (cenario === 'senha2') {
  // sair do campo de senha CLICANDO no campo comum (Tab é recusado com o foco na senha) e digitar nele
  const exe = process.env.SORA_QA_JANELA_EXE;
  ps('limpar');
  spawn(exe, ['senha', '140', '140'], { detached: true, stdio: 'ignore' }).unref();
  await espera(1500);
  ps('foco-processo', 'janela-qa');
  await espera(600);
  const obs = await observar(join(tmp, 'obs-senha2.png'));
  const comum = obs.arvore.find(e => e.papel === 'campo de texto' && /Campo comum/.test(e.nome));
  console.log('campo comum:', JSON.stringify(comum));
  const clique = await agir({ tipo: 'clicar', ponto: comum.centro, janela_programa: 'janela-qa.exe' }, 60);
  console.log('clicar no campo comum →', JSON.stringify(clique));
  const dig = await agir({ tipo: 'digitar', texto: 'texto comum ok', janela_programa: 'janela-qa.exe' }, 20);
  console.log('digitar no campo comum →', JSON.stringify(dig));
  const depois = await observar(join(tmp, 'obs-senha2b.png'));
  console.log('valores:', JSON.stringify(depois.arvore.filter(e => e.papel === 'campo de texto')));
  ps('limpar');
}

if (cenario === 'bloqueado') {
  // programas bloqueados que o QA abre (nunca os do usuário): cmd e o PowerShell
  const lancadores = [
    ['cmd.exe', "Start-Process cmd.exe -WindowStyle Normal -ArgumentList '/k','title QA-bloqueado'"],
    ['powershell.exe', `Start-Process powershell.exe -WindowStyle Normal -ArgumentList '-NoExit','-EncodedCommand','${Buffer.from("$Host.UI.RawUI.WindowTitle='QA-bloqueado-ps'", 'utf16le').toString('base64')}'`],
  ];
  for (const [nome, comandoPs] of lancadores) {
    const filho = { pid: 0 };
    // aberto por Start-Process (cria o console de verdade; um spawn desanexado do node não cria janela)
    execFileSync('powershell', ['-NoProfile', '-Command', comandoPs]);
    // o Windows Terminal demora a abrir a janela: tenta por até ~12 s
    let achou = false;
    for (let i = 0; i < 24 && !achou; i++) { await espera(500); try { ps('foco-titulo', 'QA-bloqueado'); achou = true; } catch { /* ainda não abriu */ } }
    assert.ok(achou, 'a janela de teste (QA-bloqueado) não abriu');
    await espera(700);
    const obs = await observar(join(tmp, `obs-${nome}.png`));
    const aviso = obs.arvore.find(e => e.papel === 'aviso');
    console.log(`${nome} na frente → captura omitida:`, Boolean(aviso), '| janela ativa:', JSON.stringify(obs.janelas.find(j => j.ativa)));
    const r = await agir({ tipo: 'digitar', texto: 'echo oi', janela_programa: 'windowsterminal.exe' }, 20);
    console.log(`${nome} → digitar:`, JSON.stringify(r));
    resultado[nome] = { omitida: Boolean(aviso), r };
    ps('fechar-titulo', 'QA-bloqueado');
    
    await espera(500);
  }
  const abertos = (await api('/v1/atencao', { token })).corpo.map(p => p.titulo);
  console.log('cartões abertos depois:', JSON.stringify(abertos));
  console.log('RESUMO', JSON.stringify(resultado));
}
process.exit(0);
