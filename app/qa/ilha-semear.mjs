// Semeia, pela API real (8200), um bot que fica "precisa de você" para a Ilha ter o que mostrar.
// Só com o modelo falso (SORA_MODELO_FALSO=1): "[pergunta]" faz o bot perguntar e esperar a resposta.
// Sempre reaproveita UM bot de QA ("Revisora QA da Ilha"); só cria se ele não existir. Antes de
// semear, apaga as conversas antigas desse bot, então rodar várias vezes não acumula nada.
// Uso:
//   node qa/ilha-semear.mjs [pergunta|aprovacao]   → imprime {agenteId, nome, conversaId}
//   node qa/ilha-semear.mjs limpar                 → apaga as conversas e o bot de QA
const API = process.env.SORA_QA_API ?? 'http://localhost:8200';
const EMAIL = process.env.SORA_QA_ILHA_EMAIL ?? 'qa-ilha-e5@sora.local';
const SENHA = process.env.SORA_QA_SENHA ?? 'sora-qa-senha-123';
const NOME_BOT = 'Revisora QA da Ilha';
const acao = process.argv[2] ?? 'pergunta';
const gatilho = acao === 'aprovacao' ? '[aprovacao]' : '[pergunta]';

const chamar = async (caminho, opcoes = {}, token) => {
  const r = await fetch(`${API}${caminho}`, { ...opcoes, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...opcoes.headers } });
  const texto = await r.text();
  return { status: r.status, corpo: texto ? JSON.parse(texto) : null };
};
const login = await chamar('/v1/auth/entrar', { method: 'POST', body: JSON.stringify({ email: EMAIL, senha: SENHA }) });
if (login.status !== 200) throw new Error(`login ${login.status}: rode antes o qa/ilha-tauri.mjs para criar a conta`);
const token = login.corpo.token_acesso;

const agentes = (await chamar('/v1/agentes', {}, token)).corpo ?? [];
let bot = agentes.find(a => a.tipo === 'individual' && a.nome === NOME_BOT);

/** Apaga as conversas do bot de QA (o bot fica, para ser reaproveitado). */
async function apagarConversasDoBot(id) {
  const conversas = (await chamar('/v1/conversas', {}, token)).corpo ?? [];
  for (const c of conversas.filter(c => c.agente_id === id)) {
    const r = await chamar(`/v1/conversas/${c.id}?manter_agentes=true`, { method: 'DELETE' }, token);
    if (r.status !== 204 && r.status !== 404) throw new Error(`apagar conversa ${c.id}: ${r.status}`);
  }
}

if (acao === 'limpar') {
  if (bot) {
    await apagarConversasDoBot(bot.id);
    const r = await chamar(`/v1/agentes/${bot.id}`, { method: 'DELETE' }, token);
    if (r.status !== 204) throw new Error(`apagar bot de QA: ${r.status}`);
  }
  console.log(JSON.stringify({ limpo: true, botApagado: Boolean(bot) }));
  process.exit(0);
}

if (bot) {
  await apagarConversasDoBot(bot.id);
} else {
  const criado = await chamar('/v1/agentes', { method: 'POST', body: JSON.stringify({ nome: NOME_BOT, funcao: 'Revisa textos para o QA da Ilha', papel: 'Bot de QA da Ilha: revisa textos curtos.' }) }, token);
  if (criado.status !== 201) throw new Error(`criar bot ${criado.status}: ${JSON.stringify(criado.corpo)}`);
  bot = criado.corpo;
}
const conversa = await chamar('/v1/conversas', { method: 'POST', body: JSON.stringify({ agente_id: bot.id, texto: `${gatilho} revise o texto do folheto`, anexos: [] }) }, token);
if (conversa.status !== 201) throw new Error(`conversa ${conversa.status}: ${JSON.stringify(conversa.corpo)}`);
console.log(JSON.stringify({ agenteId: bot.id, nome: bot.nome, conversaId: conversa.corpo.id }));
