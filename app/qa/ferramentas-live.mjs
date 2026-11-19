// Faro-3: prova AO VIVO das chamadas de ferramenta com modelo real (Groq), pela API REST + SSE.
// Biblioteca + cenarios em ferramentas-live-cenarios.mjs. A chave da Groq e lida de
// ../backend/.env em tempo de execucao e nunca e impressa.
// Estado (conta de QA) fica em qa/shots/ferramentas-live/estado.json.
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const API = process.env.SORA_QA_API ?? 'http://localhost:8200';
const aqui = dirname(fileURLToPath(import.meta.url));
export const SAIDA = join(aqui, 'shots', 'ferramentas-live');
mkdirSync(SAIDA, { recursive: true });
const ESTADO = join(SAIDA, 'estado.json');
const SENHA = 'sora-qa-senha-123';
export const dorme = (ms) => new Promise((r) => setTimeout(r, ms));

export async function http(token, metodo, caminho, corpo) {
  const ehForm = corpo instanceof FormData;
  const resp = await fetch(API + caminho, {
    method: metodo,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(corpo !== undefined && !ehForm ? { 'Content-Type': 'application/json' } : {}),
    },
    body: corpo === undefined ? undefined : ehForm ? corpo : JSON.stringify(corpo),
  });
  const txt = await resp.text();
  let dados = null;
  try { dados = txt ? JSON.parse(txt) : null; } catch { dados = txt; }
  return { status: resp.status, dados };
}

function convite() {
  const codigo = `QA-${Date.now().toString(36).toUpperCase()}`;
  execFileSync('uv', ['run', 'python', '-m', 'app.cli', 'convite', 'criar', '--codigo', codigo, '--usos', '1'],
    { cwd: join(aqui, '..', '..', 'backend'), env: { ...process.env, AMBIENTE: 'desenvolvimento' }, stdio: 'ignore', shell: process.platform === 'win32' });
  return codigo;
}

export async function sessao() {
  let est = existsSync(ESTADO) ? JSON.parse(readFileSync(ESTADO, 'utf8')) : null;
  if (!est) {
    est = { email: `faro3-${Date.now()}@sora.local` };
    const c = await http(null, 'POST', '/v1/auth/cadastrar', { nome: 'Faro3 QA', email: est.email, senha: SENHA, convite: convite() });
    if (c.status !== 201) throw new Error(`cadastro ${c.status} ${JSON.stringify(c.dados)}`);
    writeFileSync(ESTADO, JSON.stringify(est));
  }
  const l = await http(null, 'POST', '/v1/auth/entrar', { email: est.email, senha: SENHA });
  if (l.status !== 200) throw new Error(`login ${l.status}`);
  const token = l.dados.token_acesso;
  if (!est.provedor) {
    const chave = readFileSync(join(aqui, '..', '..', 'backend', '.env'), 'utf8').match(/^SORA_QA_GROQ_CHAVE\s*=\s*(.+)$/m)?.[1].trim().replace(/^['"]|['"]$/g, '');
    if (!chave) throw new Error('chave ausente');
    const p = await http(token, 'POST', '/v1/provedores', { tipo: 'groq', chave });
    if (p.status !== 201) throw new Error(`provedor ${p.status}`);
    est.provedor = true;
    writeFileSync(ESTADO, JSON.stringify(est));
  }
  return { token, est };
}

/** Le o SSE da conversa em segundo plano. */
export function ouvir(token, conversaId) {
  const eventos = []; const ctl = new AbortController(); const t0 = Date.now();
  (async () => {
    try {
      const resp = await fetch(`${API}/v1/conversas/${conversaId}/eventos`, { headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' }, signal: ctl.signal });
      const dec = new TextDecoder(); let buf = '';
      for await (const bloco of resp.body) {
        buf += dec.decode(bloco, { stream: true });
        let i;
        while ((i = buf.search(/\r?\n\r?\n/)) >= 0) {
          const cru = buf.slice(0, i); buf = buf.slice(i).replace(/^\r?\n\r?\n/, '');
          let nome = 'message'; const dados = [];
          for (const ln of cru.split(/\r?\n/)) {
            if (ln.startsWith('event:')) nome = ln.slice(6).trim();
            else if (ln.startsWith('data:')) dados.push(ln.slice(5).trim());
          }
          if (nome === 'ping' || !dados.length) continue;
          let d; try { d = JSON.parse(dados.join('\n')); } catch { d = dados.join('\n'); }
          eventos.push({ t: Date.now() - t0, ev: nome, d });
        }
      }
    } catch (e) { if (e.name !== 'AbortError') eventos.push({ t: Date.now() - t0, ev: '_erro_sse', d: String(e) }); }
  })();
  return { eventos, fechar: () => ctl.abort() };
}

const MARCOS = ['mensagem.fim', 'pergunta', 'aprovacao.pedida', 'erro', 'bot.rascunho', 'grupo.proposto'];

/** Espera o turno acabar: um marco (fim de mensagem, pergunta...) e depois 'quietoMs' sem evento novo. */
export async function esperar(ouv, { max = 150000, quietoMs = 8000, desde = 0 } = {}) {
  const ini = Date.now();
  while (Date.now() - ini < max) {
    await dorme(1000);
    if (!ouv.eventos.slice(desde).some((e) => MARCOS.includes(e.ev))) continue;
    const n = ouv.eventos.length;
    await dorme(quietoMs);
    if (ouv.eventos.length === n) return true;
  }
  return false;
}

export function resumo(eventos, desde = 0) {
  const linhas = []; const textos = new Map(); const fluxos = new Map();
  for (const { t, ev, d } of eventos.slice(desde)) {
    const ts = `${(t / 1000).toFixed(1)}s`;
    if (ev === 'mensagem.inicio') textos.set(d.mensagem_id, { autor: d.autor, texto: '' });
    else if (ev === 'mensagem.delta') { const m = textos.get(d.mensagem_id); if (m) m.texto += d.texto; }
    else if (ev === 'mensagem.fim') linhas.push(`${ts} msg.fim [${textos.get(d.mensagem_id)?.autor}] ${JSON.stringify((textos.get(d.mensagem_id)?.texto ?? '').slice(0, 500))} estado=${d.estado} fontes=${d.fontes?.length ?? 0} anexos=${d.anexos?.length ?? 0}`);
    else if (ev === 'passo') linhas.push(`${ts} passo ${d.tipo}/${d.status} ${d.ferramenta ?? ''} ${d.acao ?? ''} ${d.parametros ? JSON.stringify(d.parametros).slice(0, 160) : ''} ${d.resultado ? '=> ' + JSON.stringify(d.resultado).slice(0, 220) : ''} ${d.tipo === 'prompt' ? '' : (d.texto ?? '').slice(0, 100)}`);
    else if (ev === 'mensagem.token') { const a = fluxos.get(d.fluxo_id); fluxos.set(d.fluxo_id, { ini: a?.ini ?? ts, t: ts, texto: d.texto, fim: d.fim, n: (a?.n ?? 0) + 1 }); }
    else if (ev === 'contexto.atualizado' || ev === 'sugestoes') continue;
    else linhas.push(`${ts} ${ev} ${JSON.stringify(d).slice(0, 300)}`);
  }
  for (const [id, f] of fluxos) linhas.push(`   previa fluxo ${id.slice(0, 8)} (${f.n} evts, de ${f.ini} ate ${f.t}, fim=${f.fim}): ${JSON.stringify(f.texto.slice(0, 300))}`);
  return linhas.join('\n');
}

export async function novaConversa(token, agenteId, texto, anexos = []) {
  const c = await http(token, 'POST', '/v1/conversas', { agente_id: agenteId, texto, anexos });
  if (c.status !== 201) throw new Error(`conversa ${c.status} ${JSON.stringify(c.dados)}`);
  return c.dados;
}

export async function enviar(token, conversaId, texto, anexos = []) {
  const r = await http(token, 'POST', `/v1/conversas/${conversaId}/mensagens`, { texto, anexos });
  if (r.status !== 202) throw new Error(`mensagem ${r.status} ${JSON.stringify(r.dados)}`);
  return r.dados;
}

/** Um turno: cria a conversa (ou manda mensagem), espera, imprime o resumo e guarda os eventos. */
export async function turno(token, { conversaId, agenteId, texto, anexos, titulo, max, quietoMs }) {
  let id = conversaId; const t0 = Date.now();
  let ouv;
  if (!id) {
    const c = await novaConversa(token, agenteId, texto, anexos); id = c.id;
    ouv = ouvir(token, id); // o stream reenvia desde o inicio (Last-Event-ID ausente)
  } else {
    ouv = ouvir(token, id);
    await dorme(600);
    await enviar(token, id, texto, anexos);
  }
  let ok = await esperar(ouv, { max, quietoMs });
  // 429 do provedor deixa o turno mudo por dezenas de segundos: so acaba quando o agente sai de "trabalhando".
  const conv = (await http(token, 'GET', '/v1/conversas')).dados.find((c) => c.id === id);
  let mudou = Date.now(), n0 = -1; const lim = Date.now() + (max ?? 150000);
  while (conv && Date.now() < lim) {
    const ag = (await http(token, 'GET', '/v1/agentes')).dados.find((a) => a.id === conv.agente_id);
    const n = ouv.eventos.length;
    if (n !== n0 || ag?.estado === 'trabalhando') { n0 = n; mudou = Date.now(); }
    if (Date.now() - mudou > 70000) break; // 70 s sem evento e sem "trabalhando": o turno acabou
    await dorme(3000);
  }
  if (Date.now() >= lim) ok = false;
  await dorme(2000);
  ouv.fechar();
  console.log(`\n=== ${titulo ?? texto.slice(0, 70)} | conversa=${id} | ${((Date.now() - t0) / 1000).toFixed(1)}s | ${ok ? 'concluiu' : 'TIMEOUT'}\n${resumo(ouv.eventos)}`);
  const ms = await mensagens(token, id);
  console.log('PERSISTIDAS:', JSON.stringify((Array.isArray(ms) ? ms : []).map((m) => ({ a: m.autor, c: m.conteudo.slice(0, 200), est: m.estado, fontes: m.fontes?.length, anexos: m.anexos?.length }))));
  writeFileSync(join(SAIDA, `${id}-${Date.now()}.json`), JSON.stringify(ouv.eventos, null, 1));
  return { id, eventos: ouv.eventos, ouv };
}

export async function soraId(token) { return (await http(token, 'GET', '/v1/agentes/sora')).dados.id; }
export async function mensagens(token, id) { return (await http(token, 'GET', `/v1/conversas/${id}/mensagens?limite=100`)).dados; }
