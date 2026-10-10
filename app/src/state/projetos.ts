// Store de projetos, equipes, agentes e trabalho (Rodada 3).
// • Estado global único (useSyncExternalStore) persistido em localStorage (com try/catch).
// • O tempo é a fonte da verdade: cada Execucao guarda `inicio` e um roteiro com tempos relativos;
//   status, %, passos visíveis e fases do projeto são DERIVADOS de `agora`. Recarregar a página
//   no meio do trabalho continua exatamente do ponto certo.
import { useEffect, useSyncExternalStore } from 'react';
import type { PassoTrabalho, Status } from '../types';
import {
  COR_SORA, duracaoRoteiro, novoId, pedeTrabalho, planejar, respostaConversa, roteiroAvulso, tituloDoChat, verboPara as verboDe,
  type AgenteSora, type EntregaGerada, type PassoRoteiro, type RascunhoAgente, type TarefaGerada,
} from '../data/planejador';

export type { AgenteSora, EntregaGerada, PassoRoteiro, RascunhoAgente, TarefaGerada };

// ---------- tipos ----------

export interface Execucao {
  id: string;
  agenteId: string;
  projetoId?: string;
  tarefaId?: string;
  inicio: number;              // ms (epoch)
  roteiro: PassoRoteiro[];
}

export interface ProjetoSora {
  id: string;
  /** 'chat': conversa iniciada no Novo chat (só vira equipe se o pedido pedir trabalho); 'projeto': sempre monta equipe */
  tipo: 'chat' | 'projeto';
  titulo: string;
  pedido: string;
  modelo: string;
  assunto: string;
  resposta: string;            // primeira fala da Sora
  criadoEm: number;
  tarefas: TarefaGerada[];
  agenteIds: string[];
  entregas: Record<string, EntregaGerada>;
  marcos: { plano: number; nascimentos: number[]; trabalho: number; fim: number };
  aprovadoEm?: number;
  versao: number;
  entregasAnteriores?: Record<string, EntregaGerada>;   // versão anterior (após um ajuste)
  ajusteAgenteId?: string;                              // agente que fez o último ajuste
}

export interface MensagemChat {
  id: string;
  conversaId: string;          // 'sora:<projetoId>' ou agenteId
  autor: 'usuario' | 'sora' | string;
  texto: string;
  criadoEm: number;            // mensagens futuras (respostas) só aparecem quando agora >= criadoEm
  execucaoId?: string;
}

export interface SoraPerfil { nome: string; cor: string }

export interface EstadoProjetos {
  versao: 1;
  sora: SoraPerfil;
  agentes: Record<string, AgenteSora>;
  projetos: ProjetoSora[];     // mais recente primeiro
  projetoAtivoId: string | null;
  execucoes: Execucao[];
  mensagens: MensagemChat[];
  pluginsConectados: string[];
}

export type FaseProjeto = 'pensando' | 'conversa' | 'planejando' | 'coordenando' | 'pronto' | 'aprovado';

// ---------- linha do tempo de um projeto novo (ms após o envio) ----------
export const TEMPOS = {
  pensar: 2600,      // thinking orb da Sora
  nascer0: 3800,     // primeiro agente "nasce"
  nascerPasso: 1500, // intervalo entre agentes
  folga: 900,        // depois do último nascimento, começa o trabalho
  handoff: 600,      // pausa entre um agente e o próximo
};

// ---------- persistência ----------
const CHAVE = 'sora.projetos.v1';
const inicial = (): EstadoProjetos => ({
  versao: 1, sora: { nome: 'Sora', cor: COR_SORA }, agentes: {}, projetos: [], projetoAtivoId: null, execucoes: [], mensagens: [],
  pluginsConectados: [...PLUGINS_PADRAO],
});

/** Plugins conectados de início (os destaques da tela Plugins). */
export const PLUGINS_PADRAO = ['Figma', 'ChatGPT', 'Gemini', 'Canva', 'Notion'];

function carregar(): EstadoProjetos {
  try {
    const bruto = localStorage.getItem(CHAVE);
    if (!bruto) return inicial();
    const e = JSON.parse(bruto) as EstadoProjetos;
    if (e?.versao !== 1 || typeof e.agentes !== 'object' || !Array.isArray(e.projetos)) return inicial();
    return { ...inicial(), ...e, projetos: e.projetos.map(p => ({ ...p, tipo: p.tipo ?? 'projeto' })) };
  } catch { return inicial(); }
}

let estado: EstadoProjetos = typeof window === 'undefined' ? inicial() : carregar();
const ouvintes = new Set<() => void>();
/** Grava NA HORA: com atraso, uma navegação/recarga logo após a mudança perdia a gravação. */
function gravar() {
  try { localStorage.setItem(CHAVE, JSON.stringify(estado)); } catch { /* armazenamento indisponível: segue só em memória */ }
}

function definir(proximo: EstadoProjetos) {
  estado = proximo;
  gravar();
  ouvintes.forEach(f => f());
  relogioReavaliar();
}
const alterar = (f: (e: EstadoProjetos) => EstadoProjetos) => definir(f(estado));

export function lerEstado() { return estado; }
function assinar(f: () => void) { ouvintes.add(f); return () => { ouvintes.delete(f); }; }

// sincroniza entre abas
if (typeof window !== 'undefined') {
  window.addEventListener('storage', ev => { if (ev.key === CHAVE) { estado = carregar(); ouvintes.forEach(f => f()); relogioReavaliar(); } });
}

// ---------- relógio compartilhado (só corre enquanto há trabalho em andamento) ----------
let agoraAtual = Date.now();
let relogio = 0;
const ouvintesRelogio = new Set<() => void>();

/** Momento (ms) em que todo o trabalho já agendado termina. */
function fimDeTudo(e: EstadoProjetos) {
  let fim = 0;
  for (const x of e.execucoes) fim = Math.max(fim, x.inicio + duracaoRoteiro(x.roteiro));
  for (const p of e.projetos) fim = Math.max(fim, p.marcos.fim);
  for (const m of e.mensagens) fim = Math.max(fim, m.criadoEm);
  return fim;
}
function relogioReavaliar() {
  if (typeof window === 'undefined') return;
  const ativo = ouvintesRelogio.size > 0 && fimDeTudo(estado) + 500 > Date.now();
  if (ativo && !relogio) {
    relogio = window.setInterval(() => {
      agoraAtual = Date.now();
      ouvintesRelogio.forEach(f => f());
      if (fimDeTudo(estado) + 500 <= agoraAtual) { window.clearInterval(relogio); relogio = 0; }
    }, 200);
  }
  if (!ativo && relogio) { window.clearInterval(relogio); relogio = 0; }
  agoraAtual = Date.now();
}
function assinarRelogio(f: () => void) {
  ouvintesRelogio.add(f); relogioReavaliar();
  return () => { ouvintesRelogio.delete(f); relogioReavaliar(); };
}

// ---------- hooks ----------

/** Estado completo do store (re-renderiza a cada mudança). */
export function useProjetos() { return useSyncExternalStore(assinar, lerEstado, lerEstado); }

/** "Agora" em ms; avança a cada 200 ms enquanto houver trabalho em andamento. */
export function useAgora() {
  const agora = useSyncExternalStore(assinarRelogio, () => agoraAtual, () => agoraAtual);
  useEffect(() => { relogioReavaliar(); }, []);
  return agora;
}

// ---------- derivados (puros) ----------

export function progressoExecucao(x: Execucao, agora: number) {
  const d = duracaoRoteiro(x.roteiro);
  return d <= 0 ? 100 : Math.max(0, Math.min(100, Math.round(((agora - x.inicio) / d) * 100)));
}

/** Passos já iniciados de uma execução, com status derivado do relógio. */
export function passosDaExecucao(x: Execucao, agora: number): PassoTrabalho[] {
  const out: PassoTrabalho[] = [];
  x.roteiro.forEach((p, i) => {
    const inicio = x.inicio + p.em;
    if (inicio > agora) return;
    const fim = inicio + p.dur;
    out.push({
      id: `${x.id}-${i}`, agenteId: x.agenteId, tipo: p.tipo, texto: p.texto, ferramenta: p.ferramenta, acao: p.acao,
      parametros: p.parametros, resultado: fim <= agora ? p.resultado : undefined,
      status: fim <= agora ? 'concluido' : 'executando', inicio, fim: fim <= agora ? fim : undefined,
      paraAgenteId: p.paraAgenteId, origem: p.origem,
    });
  });
  return out;
}

export function execucoesDoAgente(e: EstadoProjetos, agenteId: string) {
  return e.execucoes.filter(x => x.agenteId === agenteId).sort((a, b) => a.inicio - b.inicio);
}

export interface EstadoAgente {
  status: Status;
  progresso: number;
  rotulo: string;              // "Pesquisando", "Aguardando referências", "Concluído", "Disponível"
  nascido: boolean;            // já apareceu (agentes de equipe nascem em sequência)
  execucao?: Execucao;         // atual (ou a última)
}

export function estadoAgente(e: EstadoProjetos, agenteId: string, agora: number): EstadoAgente {
  const ag = e.agentes[agenteId];
  if (!ag) return { status: 'aguardando', progresso: 0, rotulo: '', nascido: false };
  const nascido = ag.criadoEm <= agora;
  const xs = execucoesDoAgente(e, agenteId);
  const atual = xs.find(x => x.inicio <= agora && agora < x.inicio + duracaoRoteiro(x.roteiro));
  if (atual) return { status: 'trabalhando', progresso: progressoExecucao(atual, agora), rotulo: ag.verbo, nascido, execucao: atual };
  const passadas = xs.filter(x => x.inicio + duracaoRoteiro(x.roteiro) <= agora);
  const futura = xs.find(x => x.inicio > agora);
  if (futura && !passadas.length) return { status: 'aguardando', progresso: 0, rotulo: ag.espera, nascido, execucao: futura };
  if (passadas.length) return { status: 'concluido', progresso: 100, rotulo: 'Concluído', nascido, execucao: passadas[passadas.length - 1] };
  return { status: 'aguardando', progresso: 0, rotulo: ag.avulso ? 'Disponível' : ag.espera, nascido };
}

export interface EstadoDoProjeto {
  fase: FaseProjeto;
  nascidos: number;            // quantos agentes já nasceram
  concluidos: number;
  pulso: number;               // conta eventos (nascimentos + conclusões) — use como pulseKey da Sora
  progresso: number;           // 0..100 do projeto inteiro
}

export function estadoProjeto(e: EstadoProjetos, p: ProjetoSora, agora: number): EstadoDoProjeto {
  const nascidos = p.marcos.nascimentos.filter(t => t <= agora).length;
  const xs = e.execucoes.filter(x => x.projetoId === p.id);
  const concluidos = p.agenteIds.filter(id => xs.some(x => x.agenteId === id && x.inicio + duracaoRoteiro(x.roteiro) <= agora)).length;
  if (!p.agenteIds.length && !p.tarefas.length) {
    return { fase: agora < p.marcos.plano ? 'pensando' : 'conversa', nascidos: 0, concluidos: 0, pulso: agora < p.marcos.plano ? 0 : 1, progresso: 0 };
  }
  const fase: FaseProjeto = p.aprovadoEm ? 'aprovado'
    : agora < p.marcos.plano ? 'pensando'
      : agora < p.marcos.trabalho ? 'planejando'
        : agora < p.marcos.fim ? 'coordenando' : 'pronto';
  const total = p.marcos.fim - p.marcos.trabalho;
  const progresso = Math.max(0, Math.min(100, Math.round(((agora - p.marcos.trabalho) / Math.max(1, total)) * 100)));
  return { fase, nascidos, concluidos, pulso: nascidos + concluidos + (fase === 'pronto' ? 1 : 0), progresso };
}

export const projetoAtivo = (e: EstadoProjetos) => e.projetos.find(p => p.id === e.projetoAtivoId) ?? null;

/** Agentes do projeto ativo já nascidos (ordem do plano). */
export function agentesDoProjeto(e: EstadoProjetos, p: ProjetoSora | null, agora: number) {
  if (!p) return [];
  return p.agenteIds.map(id => e.agentes[id]).filter((a): a is AgenteSora => !!a && a.criadoEm <= agora);
}

/** Agentes avulsos (criados no estúdio), mais recentes primeiro. */
export const agentesAvulsos = (e: EstadoProjetos) =>
  Object.values(e.agentes).filter(a => a.avulso).sort((a, b) => b.criadoEm - a.criadoEm);

/** Todos os agentes (equipes + avulsos), para o estúdio. */
export const todosAgentes = (e: EstadoProjetos, agora: number) =>
  Object.values(e.agentes).filter(a => a.criadoEm <= agora).sort((a, b) => b.criadoEm - a.criadoEm);

/** Mensagens visíveis de uma conversa. */
export const mensagensDa = (e: EstadoProjetos, conversaId: string, agora: number) =>
  e.mensagens.filter(m => m.conversaId === conversaId && m.criadoEm <= agora).sort((a, b) => a.criadoEm - b.criadoEm);

/** Passos de trabalho de um agente (todas as execuções já iniciadas). */
export function passosDoAgente(e: EstadoProjetos, agenteId: string, agora: number) {
  return execucoesDoAgente(e, agenteId).flatMap(x => passosDaExecucao(x, agora));
}

// ---------- ações ----------

const usados = (e: EstadoProjetos) => ({
  nomesEmUso: Object.values(e.agentes).map(a => a.nome),
  coresEmUso: Object.values(e.agentes).map(a => a.cor),
});

const PENSAR_CONVERSA = 1600;

/**
 * Novo chat/projeto a partir da primeira mensagem.
 * • tipo 'projeto' (padrão): a Sora pensa, planeja e cria a equipe inteira.
 * • tipo 'chat': se a mensagem pede trabalho, idem; se é só conversa, a Sora apenas responde.
 */
export function criarProjeto(pedido: string, agora = Date.now(), opcoes: { tipo?: 'chat' | 'projeto' } = {}): ProjetoSora {
  const tipo = opcoes.tipo ?? 'projeto';
  if (tipo === 'chat' && !pedeTrabalho(pedido)) {
    const projeto: ProjetoSora = {
      id: novoId('chat'), tipo, titulo: tituloDoChat(pedido), pedido, modelo: 'conversa', assunto: '', resposta: '',
      criadoEm: agora, tarefas: [], agenteIds: [], entregas: {},
      marcos: { plano: agora + PENSAR_CONVERSA, nascimentos: [], trabalho: agora + PENSAR_CONVERSA, fim: agora + PENSAR_CONVERSA }, versao: 1,
    };
    const conversa = `sora:${projeto.id}`;
    alterar(e => ({
      ...e, projetos: [projeto, ...e.projetos], projetoAtivoId: projeto.id,
      mensagens: [...e.mensagens,
        { id: novoId('msg'), conversaId: conversa, autor: 'usuario', texto: pedido, criadoEm: agora },
        { id: novoId('msg'), conversaId: conversa, autor: 'sora', texto: respostaConversa(pedido), criadoEm: agora + PENSAR_CONVERSA },
      ],
    }));
    return projeto;
  }
  return montarEquipe(null, pedido, agora, tipo);
}

/** Planeja e cria a equipe — num projeto novo ou dentro de um chat que já existe. */
function montarEquipe(base: ProjetoSora | null, pedido: string, agora: number, tipo: 'chat' | 'projeto'): ProjetoSora {
  const nascimentos: number[] = [];
  const plano = planejar(pedido, {
    ...usados(estado),
    criadoEm: i => { const t = agora + TEMPOS.nascer0 + i * TEMPOS.nascerPasso; nascimentos[i] = t; return t; },
  });
  const projetoId = base?.id ?? plano.agentes[0]?.projetoId ?? novoId('proj');
  const agentesNovos = plano.agentes.map(a => ({ ...a, projetoId }));
  const trabalho = (nascimentos[nascimentos.length - 1] ?? agora + TEMPOS.nascer0) + TEMPOS.folga;
  const execucoes: Execucao[] = [];
  let t = trabalho;
  for (const tarefa of plano.tarefas) {
    const roteiro = plano.roteiros[tarefa.agenteId];
    execucoes.push({ id: novoId('exec'), agenteId: tarefa.agenteId, projetoId, tarefaId: tarefa.id, inicio: t, roteiro });
    t += duracaoRoteiro(roteiro) + TEMPOS.handoff;
  }
  const fim = t - TEMPOS.handoff;
  const projeto: ProjetoSora = {
    id: projetoId, tipo: base?.tipo ?? tipo, titulo: plano.titulo, pedido,
    modelo: plano.modelo, assunto: plano.assunto, resposta: plano.resposta,
    criadoEm: base?.criadoEm ?? agora, tarefas: plano.tarefas, agenteIds: agentesNovos.map(a => a.id), entregas: plano.entregas,
    marcos: { plano: agora + TEMPOS.pensar, nascimentos, trabalho, fim }, versao: 1,
  };
  const conversa = `sora:${projetoId}`;
  alterar(e => ({
    ...e,
    agentes: { ...e.agentes, ...Object.fromEntries(agentesNovos.map(a => [a.id, a])) },
    projetos: base ? e.projetos.map(p => p.id === base.id ? projeto : p) : [projeto, ...e.projetos],
    projetoAtivoId: projetoId,
    execucoes: [...e.execucoes, ...execucoes],
    mensagens: [...e.mensagens,
      { id: novoId('msg'), conversaId: conversa, autor: 'usuario', texto: pedido, criadoEm: agora },
      { id: novoId('msg'), conversaId: conversa, autor: 'sora', texto: plano.resposta, criadoEm: agora + TEMPOS.pensar },
      { id: novoId('msg'), conversaId: conversa, autor: 'sora', criadoEm: trabalho,
        texto: `${listaNomes(agentesNovos.map(a => a.nome))} já estão trabalhando. Acompanhe pela barra lateral.` },
      { id: novoId('msg'), conversaId: conversa, autor: 'sora', criadoEm: fim, texto: 'Pronto! Revise as entregas antes de publicar.' },
    ],
  }));
  return projeto;
}

const listaNomes = (n: string[]) => n.length < 2 ? (n[0] ?? '') : `${n.slice(0, -1).join(', ')} e ${n[n.length - 1]}`;

/** "Novo chat": volta ao estado só-Sora (projetos anteriores continuam na lista). */
export function novoChat() { alterar(e => ({ ...e, projetoAtivoId: null })); }
export function abrirProjeto(id: string) { alterar(e => ({ ...e, projetoAtivoId: id })); }
export function aprovarProjeto(id: string, agora = Date.now()) {
  alterar(e => ({
    ...e,
    projetos: e.projetos.map(p => p.id === id ? { ...p, aprovadoEm: agora } : p),
    mensagens: [...e.mensagens, { id: novoId('msg'), conversaId: `sora:${id}`, autor: 'sora', criadoEm: agora + 400,
      texto: 'Aprovado! Registrei sua aprovação — a equipe pode seguir com a publicação.' }],
  }));
}
/**
 * Apaga um projeto (chat da Sora + plano + execuções). Por padrão apaga também os agentes da equipe;
 * com `manterAgentes` eles continuam existindo como agentes avulsos.
 */
export function removerProjeto(id: string, opcoes: { manterAgentes?: boolean } = {}) {
  alterar(e => {
    const p = e.projetos.find(x => x.id === id);
    const ids = new Set(p?.agenteIds ?? []);
    const agentes = opcoes.manterAgentes
      ? Object.fromEntries(Object.entries(e.agentes).map(([k, a]) => [k, ids.has(k) ? { ...a, avulso: true, projetoId: '', espera: 'Disponível' } : a]))
      : Object.fromEntries(Object.entries(e.agentes).filter(([k]) => !ids.has(k)));
    return {
      ...e,
      projetos: e.projetos.filter(x => x.id !== id),
      projetoAtivoId: e.projetoAtivoId === id ? null : e.projetoAtivoId,
      agentes,
      execucoes: e.execucoes.filter(x => x.projetoId !== id),
      mensagens: e.mensagens.filter(m => m.conversaId !== `sora:${id}` && (opcoes.manterAgentes || !ids.has(m.conversaId))),
    };
  });
}

export function renomearProjeto(id: string, titulo: string) {
  const t = titulo.trim();
  if (!t) return;
  alterar(e => ({ ...e, projetos: e.projetos.map(p => p.id === id ? { ...p, titulo: t } : p) }));
}

/** Mensagem direta do usuário a um agente: o agente trabalha (passos ao vivo) e responde. */
export function enviarParaAgente(agenteId: string, texto: string, agora = Date.now(), registrarNoChat = true) {
  const ag = estado.agentes[agenteId];
  if (!ag) return;
  const ocupadoAte = Math.max(agora + 500, ...execucoesDoAgente(estado, agenteId).map(x => x.inicio + duracaoRoteiro(x.roteiro) + 300));
  const roteiro = roteiroAvulso(ag, texto);
  const x: Execucao = { id: novoId('exec'), agenteId, projetoId: ag.avulso ? undefined : ag.projetoId, inicio: ocupadoAte, roteiro };
  const fim = ocupadoAte + duracaoRoteiro(roteiro);
  const entrega = roteiro.find(p => p.tipo === 'entrega');
  alterar(e => ({
    ...e,
    execucoes: [...e.execucoes, x],
    mensagens: [...e.mensagens,
      { id: novoId('msg'), conversaId: agenteId, autor: registrarNoChat ? 'usuario' : 'sora', texto, criadoEm: agora },
      { id: novoId('msg'), conversaId: agenteId, autor: agenteId, criadoEm: fim, execucaoId: x.id,
        texto: `Feito. ${entrega?.resultado?.resumo ?? 'Pronto'} — veja os passos no painel Trabalho.` },
    ],
  }));
  return x;
}

/** Pedido de ajuste num projeto: a Sora repassa ao agente certo e uma nova versão é gerada. */
export function pedirAjuste(projetoId: string, texto: string, agenteId?: string, agora = Date.now()) {
  const p = estado.projetos.find(x => x.id === projetoId);
  if (!p) return;
  const t = texto.toLowerCase();
  const ags = p.agenteIds.map(id => estado.agentes[id]).filter(Boolean);
  const porPalavra = ags.find(a => t.split(/\s+/).some(w => w.length > 4 && (a.funcao.toLowerCase().includes(w.slice(0, 5)) || a.nome.toLowerCase() === w)));
  // pelo tipo do que precisa mudar: textos → quem entregou texto/calendário; visual → quem entregou imagens
  const querTexto = /texto|legenda|escrev|tom|descontra|formal|se[cç][oõ]es|roteiro/.test(t);
  const querVisual = /imag|foto|cor|visual|pe[cç]a|layout|tela|cena/.test(t);
  const porTipo = querTexto ? (ags.find(a => /texto|roteir|resum|relat|legend/i.test(a.funcao)) ?? ags.find(a => ['texto', 'calendario'].includes(p.entregas[a.id]?.tipo ?? '')))
    : querVisual ? (ags.find(a => /visual|design|cena|layout/i.test(a.funcao)) ?? ags.find(a => p.entregas[a.id]?.tipo === 'imagem')) : undefined;
  const alvo = (agenteId && estado.agentes[agenteId]) || porPalavra || porTipo || ags[ags.length - 1];
  if (!alvo) return;
  const x = enviarParaAgente(alvo.id, texto, agora, false);
  const anterior = p.entregas[alvo.id];
  const nova: EntregaGerada | undefined = anterior && {
    ...anterior,
    resumo: `${anterior.resumo} · v${p.versao + 1}`,
    itens: [...(anterior.itens ?? []).slice(0, 5), `Ajuste: ${texto}`],
  };
  const conversa = `sora:${projetoId}`;
  alterar(e => ({
    ...e,
    projetos: e.projetos.map(q => q.id === projetoId ? {
      ...q, versao: q.versao + 1, aprovadoEm: undefined, ajusteAgenteId: alvo.id,
      entregasAnteriores: { ...q.entregas }, entregas: nova ? { ...q.entregas, [alvo.id]: nova } : q.entregas,
      marcos: { ...q.marcos, fim: Math.max(q.marcos.fim, x ? x.inicio + duracaoRoteiro(x.roteiro) : 0) },
    } : q),
    mensagens: [...e.mensagens,
      { id: novoId('msg'), conversaId: conversa, autor: 'usuario', texto, criadoEm: agora },
      { id: novoId('msg'), conversaId: conversa, autor: 'sora', texto: `Pedi para ${alvo.nome} ajustar. Já te mostro a nova versão.`, criadoEm: agora + 900 },
      ...(x ? [{ id: novoId('msg'), conversaId: conversa, autor: 'sora', texto: 'Pronto. Veja a nova versão.', criadoEm: x.inicio + duracaoRoteiro(x.roteiro) }] : []),
    ],
  }));
}

/**
 * Mensagem para a Sora no chat dela. Sem projeto ativo → vira um pedido (cria a equipe).
 * Projeto pronto/aprovado → vira ajuste. Durante o trabalho → a Sora responde e anota.
 */
export function conversarComSora(texto: string, agora = Date.now()) {
  const p = projetoAtivo(estado);
  if (!p) return criarProjeto(texto, agora, { tipo: 'chat' });
  const fase = estadoProjeto(estado, p, agora).fase;
  if (!p.agenteIds.length && !p.tarefas.length) {
    if (pedeTrabalho(texto)) return montarEquipe(p, texto, agora, p.tipo);
    alterar(e => ({
      ...e,
      mensagens: [...e.mensagens,
        { id: novoId('msg'), conversaId: `sora:${p.id}`, autor: 'usuario', texto, criadoEm: agora },
        { id: novoId('msg'), conversaId: `sora:${p.id}`, autor: 'sora', texto: respostaConversa(texto), criadoEm: agora + 1200 },
      ],
      projetos: e.projetos.map(q => q.id === p.id ? { ...q, marcos: { ...q.marcos, plano: agora + 1200, fim: agora + 1200 } } : q),
    }));
    return p;
  }
  if (fase === 'pronto' || fase === 'aprovado') { pedirAjuste(p.id, texto, undefined, agora); return p; }
  const conversa = `sora:${p.id}`;
  const resposta = fase === 'pensando' || fase === 'planejando'
    ? `Anotado: “${resumir(texto)}”. Vou considerar isso no plano.`
    : `Anotado: “${resumir(texto)}”. Repasso para a equipe e te aviso quando terminar.`;
  alterar(e => ({
    ...e,
    mensagens: [...e.mensagens,
      { id: novoId('msg'), conversaId: conversa, autor: 'usuario', texto, criadoEm: agora },
      { id: novoId('msg'), conversaId: conversa, autor: 'sora', texto: resposta, criadoEm: agora + 1100 },
    ],
  }));
  return p;
}
const resumir = (t: string) => t.length > 70 ? `${t.slice(0, 67).trimEnd()}…` : t;

export function alternarPlugin(nome: string) {
  alterar(e => ({
    ...e,
    pluginsConectados: e.pluginsConectados.includes(nome) ? e.pluginsConectados.filter(n => n !== nome) : [...e.pluginsConectados, nome],
  }));
}

/** Cria (sem id) ou atualiza (com id) um agente. Novos agentes do estúdio são avulsos. */
export function salvarAgente(dados: RascunhoAgente & { id?: string }): AgenteSora {
  const existente = dados.id ? estado.agentes[dados.id] : undefined;
  const ag: AgenteSora = existente
    ? { ...existente, ...dados, id: existente.id }
    : {
      id: novoId('ag'), projetoId: '', nome: dados.nome.trim() || 'Agente', funcao: dados.funcao.trim() || 'Assistente',
      cor: dados.cor, tipoMovimento: dados.tipoMovimento, ferramentas: dados.ferramentas, status: 'aguardando',
      verbo: verboDe(dados.funcao), espera: 'Disponível', instrucoes: dados.instrucoes, avulso: true, criadoEm: Date.now(),
    };
  if (existente && dados.funcao !== existente.funcao) ag.verbo = verboDe(dados.funcao);
  alterar(e => ({ ...e, agentes: { ...e.agentes, [ag.id]: ag } }));
  return ag;
}

/** Personalização rápida de qualquer agente (nome, cor, movimento, ferramentas, instruções…). */
export function atualizarAgente(id: string, patch: Partial<Omit<AgenteSora, 'id'>>) {
  const ag = estado.agentes[id];
  if (!ag) return;
  const novo = { ...ag, ...patch };
  if (patch.funcao && patch.funcao !== ag.funcao && !patch.verbo) novo.verbo = verboDe(patch.funcao);
  alterar(e => ({ ...e, agentes: { ...e.agentes, [id]: novo } }));
}

/** Remove um agente avulso (agentes de equipe saem junto com o projeto). */
/** Apaga um agente (avulso ou de equipe — na equipe, ele sai do projeto). A Sora não pode ser apagada. */
export function removerAgente(id: string) {
  alterar(e => {
    if (!e.agentes[id]) return e;
    const agentes = { ...e.agentes }; delete agentes[id];
    return {
      ...e, agentes,
      projetos: e.projetos.map(p => p.agenteIds.includes(id) ? { ...p, agenteIds: p.agenteIds.filter(x => x !== id) } : p),
      execucoes: e.execucoes.filter(x => x.agenteId !== id),
      mensagens: e.mensagens.filter(m => m.conversaId !== id),
    };
  });
}

export function atualizarSora(patch: Partial<SoraPerfil>) { alterar(e => ({ ...e, sora: { ...e.sora, ...patch } })); }
export function restaurarSora() { alterar(e => ({ ...e, sora: { nome: 'Sora', cor: COR_SORA } })); }

/** Zera tudo (QA / "começar do zero"). */
export function limparTudo() { definir(inicial()); }

// Ganchos de QA (só em desenvolvimento): qa/shoot.mjs usa para semear projetos já concluídos.
if (import.meta.env.DEV && typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).__sora = { criarProjeto, limparTudo, lerEstado, novoChat, abrirProjeto };
}
