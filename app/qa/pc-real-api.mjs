// Ajuda do teste real do C3: age como o USUÁRIO pela API (lista/decide cartões "Precisa de você", estado do PC).
// Uso: node qa/pc-real-api.mjs atencao | estado | decidir <id> <permitir|sempre_permitir|negar> | decidir-tudo <decisao> | limpar
//   env: SORA_QA_API (padrão http://localhost:8200), SORA_QA_DESK_EMAIL, SORA_QA_SENHA
import { QA_SENHA } from './entrar.mjs';

const API = process.env.SORA_QA_API ?? 'http://localhost:8200';
const EMAIL = process.env.SORA_QA_DESK_EMAIL ?? 'qa-desktop-real@sora.local';
async function api(caminho, { token, method = 'GET', body } = {}) {
  const r = await fetch(`${API}${caminho}`, { method, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: body ? JSON.stringify(body) : undefined });
  const t = await r.text();
  return { status: r.status, corpo: t ? JSON.parse(t) : null };
}
const entrada = await api('/v1/auth/entrar', { method: 'POST', body: { email: EMAIL, senha: QA_SENHA } });
if (entrada.status !== 200) { console.error('login de QA falhou', entrada.status); process.exit(2); }
const token = entrada.corpo.token_acesso;
const [cmd, a1, a2] = process.argv.slice(2);
const resumo = p => ({ id: p.id, tipo: p.tipo, acao: p.acao, titulo: p.titulo, resumo: (p.resumo ?? '').slice(0, 160), opcoes: p.opcoes?.map?.(o => o.valor ?? o) ?? p.decisoes });
if (cmd === 'atencao') {
  console.log(JSON.stringify((await api('/v1/atencao', { token })).corpo.map(resumo), null, 1));
} else if (cmd === 'estado') {
  console.log(JSON.stringify((await api('/v1/computador-pc/estado', { token })).corpo));
} else if (cmd === 'decidir') {
  const r = await api(`/v1/aprovacoes/${a1}/decidir`, { token, method: 'POST', body: { decisao: a2 } });
  console.log('decidir →', r.status, r.corpo ? JSON.stringify(r.corpo) : '');
} else if (cmd === 'decidir-tudo' || cmd === 'limpar') {
  const decisao = cmd === 'limpar' ? 'negar' : a1;
  for (const p of (await api('/v1/atencao', { token })).corpo) {
    const [caminho, corpo] = p.tipo === 'pergunta' ? [`/v1/perguntas/${p.id}/responder`, { valor: p.opcoes?.[0]?.valor ?? 'cancelar' }] : [`/v1/aprovacoes/${p.id}/decidir`, { decisao }];
    const r = await api(caminho, { token, method: 'POST', body: corpo });
    console.log(p.titulo, '→', decisao, r.status);
  }
} else { console.error('comando?'); process.exit(1); }
