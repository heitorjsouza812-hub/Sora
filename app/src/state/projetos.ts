// Estado real de conversas, equipes e trabalho. A API hidrata o estado e os eventos SSE são
// a única fonte das transições ao vivo. O relógio serve apenas para mostrar duração na interface.
import { useEffect, useSyncExternalStore } from 'react';
import { api } from '../api/cliente';
import { acompanharEventos, type EventoSse } from '../api/eventos';
import { enviarAnexo } from '../api/anexos';
import type { Anexo } from '../components/anexos';
import type { Movimento, PassoTrabalho, Status } from '../types';
import { aplicarEvento } from './aplicarEvento';

export const COR_SORA = '#E2ECFF';
export const PLUGINS_PADRAO: string[] = [];

export interface RascunhoAgente { nome: string; funcao: string; cor: string; tipoMovimento: Movimento; ferramentas: string[]; instrucoes: string }
export interface TarefaGerada { id: string; titulo: string; ordem: number; dependeDe: string[]; agenteId: string; status?: Status; progresso?: number }
export interface EntregaGerada {
  id?: string; agenteId?: string; versao?: number; tipo: 'links' | 'imagem' | 'texto' | 'calendario' | 'arquivo';
  titulo: string; resumo: string; links?: { titulo: string; dominio: string }[]; imagens?: string[]; itens?: string[]; conteudo?: unknown;
}
export type PassoRoteiro = PassoTrabalho;

export interface AgenteSora {
  id: string; projetoId: string; conversaId?: string; nome: string; funcao: string; cor: string; tipoMovimento: Movimento;
  ferramentas: string[]; status: Status; verbo: string; espera: string; instrucoes: string; avulso: boolean; criadoEm: number;
}
export interface Execucao {
  id: string; agenteId: string; projetoId?: string; tarefaId?: string; inicio: number; roteiro: PassoTrabalho[];
  status: 'pendente' | 'executando' | 'concluida' | 'falhou' | 'cancelada'; progresso: number;
}
export interface ProjetoSora {
  id: string; tipo: 'chat' | 'projeto'; titulo: string; pedido: string; modelo: string; assunto: string; resposta: string;
  criadoEm: number; tarefas: TarefaGerada[]; agenteIds: string[]; entregas: Record<string, EntregaGerada>;
  marcos: { plano: number; nascimentos: number[]; trabalho: number; fim: number };
  aprovadoEm?: number; aprovadaVersao?: number | null; versao: number; entregasAnteriores?: Record<string, EntregaGerada>;
  ajusteAgenteId?: string; cadeiaId?: string; cadeiaStatus?: 'planejando' | 'executando' | 'verificando' | 'aguardando_usuario' | 'concluida' | 'falhou' | 'cancelada';
  roteamento?: 'direto' | 'cadeia' | 'pergunta'; erro?: string; mensagensPendentes?: boolean;
}
export interface MensagemChat {
  id: string; conversaId: string; autor: 'usuario' | 'sora' | string; agenteId?: string; texto: string; criadoEm: number;
  gerando?: boolean; interrompidaEm?: number; avaliacao?: 'positiva' | 'negativa'; origem?: 'conversa'; variante?: number; anexos?: AnexoMsg[];
}
export interface AnexoMsg { id: string; nome: string; tipo: string; tamanho: number }
export interface SoraPerfil { nome: string; cor: string }
export interface EstadoProjetos {
  versao: 2; sora: SoraPerfil; agentes: Record<string, AgenteSora>; projetos: ProjetoSora[]; projetoAtivoId: string | null;
  execucoes: Execucao[]; mensagens: MensagemChat[]; pluginsConectados: string[]; carregando: boolean; erro?: string;
}
export type FaseProjeto = 'pensando' | 'conversa' | 'planejando' | 'coordenando' | 'pronto' | 'aprovado' | 'erro';

interface ConversaApi { id: string; agente_id: string; tipo: 'chat' | 'projeto' | 'agente'; titulo: string | null; aprovada_versao: number | null; criada_em: string; atualizada_em: string }
interface AgenteApi { id: string; tipo: 'sora' | 'individual' | 'especialista'; nome: string; funcao: string; cor: string; movimento: Movimento; status: Status | null }
interface MensagemApi { id: string; conversa_id: string; autor: 'usuario' | 'sora' | 'agente' | 'sistema'; agente_id?: string | null; conteudo: string; anexos: AnexoMsg[]; criada_em: string }
interface EntregasApi { entregas: { id: string; agente_id: string | null; versao: number; tipo: EntregaGerada['tipo']; titulo: string; resumo: string; conteudo: unknown }[]; versoes: number[] }

const inicial = (): EstadoProjetos => ({ versao: 2, sora: { nome: 'Sora', cor: COR_SORA }, agentes: {}, projetos: [], projetoAtivoId: null, execucoes: [], mensagens: [], pluginsConectados: [], carregando: true });
let estado = inicial();
const ouvintes = new Set<() => void>();
const notificar = () => ouvintes.forEach(f => f());
function definir(proximo: EstadoProjetos) { estado = proximo; notificar(); }
const alterar = (fn: (e: EstadoProjetos) => EstadoProjetos) => definir(fn(estado));
export const lerEstado = () => estado;
const assinar = (fn: () => void) => { ouvintes.add(fn); return () => { ouvintes.delete(fn); }; };
export function useProjetos() { return useSyncExternalStore(assinar, lerEstado, lerEstado); }

let agoraAtual = Date.now();
const ouvintesAgora = new Set<() => void>();
let timerAgora = 0;
function assinarAgora(fn: () => void) {
  ouvintesAgora.add(fn);
  if (!timerAgora && typeof window !== 'undefined') timerAgora = window.setInterval(() => { agoraAtual = Date.now(); ouvintesAgora.forEach(f => f()); }, 1000);
  return () => { ouvintesAgora.delete(fn); if (!ouvintesAgora.size && timerAgora) { window.clearInterval(timerAgora); timerAgora = 0; } };
}
export function useAgora() { const agora = useSyncExternalStore(assinarAgora, () => agoraAtual, () => agoraAtual); useEffect(() => { agoraAtual = Date.now(); }, []); return agora; }

const verboPara = (funcao: string) => /pesquis|refer/i.test(funcao) ? 'Pesquisando' : /texto|red|copy/i.test(funcao) ? 'Escrevendo' : /design|visual|imag/i.test(funcao) ? 'Criando' : 'Trabalhando';
function agenteDaApi(a: AgenteApi): AgenteSora {
  return { id: a.id, projetoId: '', nome: a.nome, funcao: a.funcao, cor: a.cor, tipoMovimento: a.movimento, ferramentas: [], status: a.status ?? 'aguardando', verbo: verboPara(a.funcao), espera: 'Aguardando', instrucoes: '', avulso: a.tipo === 'individual', criadoEm: Date.now() };
}
function projetoDaApi(c: ConversaApi): ProjetoSora {
  const criadoEm = Date.parse(c.criada_em);
  return { id: c.id, tipo: c.tipo === 'projeto' ? 'projeto' : 'chat', titulo: c.titulo || 'Nova conversa', pedido: '', modelo: '', assunto: c.titulo || '', resposta: '', criadoEm, tarefas: [], agenteIds: [], entregas: {}, marcos: { plano: criadoEm, nascimentos: [], trabalho: criadoEm, fim: criadoEm }, aprovadoEm: c.aprovada_versao ? Date.parse(c.atualizada_em) : undefined, aprovadaVersao: c.aprovada_versao, versao: 1 };
}
function mensagemDaApi(m: MensagemApi): MensagemChat {
  const autor = m.autor === 'agente' && m.agente_id ? m.agente_id : m.autor === 'usuario' ? 'usuario' : 'sora';
  return { id: m.id, conversaId: m.conversa_id, autor, agenteId: m.agente_id ?? undefined, texto: m.conteudo, criadoEm: Date.parse(m.criada_em), anexos: m.anexos, gerando: false };
}

let controladorGeral: AbortController | null = null;
const controladoresConversa = new Map<string, AbortController>();
let iniciando: Promise<void> | null = null;

function receber(evento: EventoSse) {
  alterar(e => aplicarEvento(e, evento));
  if (evento.tipo === 'entrega' || (evento.tipo === 'cadeia.atualizada' && evento.dados.status === 'concluida')) {
    const conversaId = String(evento.dados.conversa_id ?? '');
    if (conversaId) void carregarEntregas(conversaId);
  }
}

async function carregarEntregas(conversaId: string): Promise<void> {
  const dados = await api.get<EntregasApi>(`/v1/conversas/${conversaId}/entregas`);
  alterar(e => ({ ...e, projetos: e.projetos.map(p => {
    if (p.id !== conversaId) return p;
    const entregas = Object.fromEntries(dados.entregas.map(x => [x.agente_id || x.id, { ...x, agenteId: x.agente_id ?? undefined, conteudo: x.conteudo, ...(typeof x.conteudo === 'object' && x.conteudo ? x.conteudo as object : {}) }]));
    return { ...p, entregas, versao: dados.versoes.at(-1) ?? p.versao };
  }) }));
}

export function acompanharConversa(conversaId: string): void {
  if (!conversaId || controladoresConversa.has(conversaId)) return;
  for (const [id, ativo] of controladoresConversa) {
    if (id !== conversaId) { ativo.abort(); controladoresConversa.delete(id); }
  }
  const controlador = new AbortController(); controladoresConversa.set(conversaId, controlador);
  void acompanharEventos(`/v1/conversas/${conversaId}/eventos`, {
    signal: controlador.signal,
    aoEvento: evento => receber({ ...evento, dados: { conversa_id: conversaId, ...evento.dados } }),
    aoErro: erro => alterar(e => ({ ...e, erro: erro instanceof Error ? erro.message : 'Canal de eventos interrompido.' })),
  }).finally(() => controladoresConversa.delete(conversaId));
}

export function iniciarProjetos(): Promise<void> {
  if (iniciando) return iniciando;
  iniciando = (async () => {
    const [conversas, agentes] = await Promise.all([api.get<ConversaApi[]>('/v1/conversas'), api.get<AgenteApi[]>('/v1/agentes')]);
    const mensagens = (await Promise.all(conversas.map(c => api.get<MensagemApi[]>(`/v1/conversas/${c.id}/mensagens`)))).flat();
    const mapa = Object.fromEntries(agentes.filter(a => a.tipo !== 'sora').map(a => [a.id, agenteDaApi(a)]));
    for (const c of conversas) { const ag = mapa[c.agente_id]; if (ag && c.tipo === 'agente') ag.conversaId = c.id; }
    definir({ ...inicial(), carregando: false, agentes: mapa, projetos: conversas.filter(c => c.tipo !== 'agente').map(projetoDaApi), mensagens: mensagens.map(mensagemDaApi) });
    for (const c of conversas.filter(c => c.tipo !== 'agente')) void carregarEntregas(c.id).catch(() => undefined);
    controladorGeral?.abort(); controladorGeral = new AbortController();
    void acompanharEventos('/v1/eventos', { signal: controladorGeral.signal, aoEvento: receber, aoErro: erro => alterar(e => ({ ...e, erro: erro instanceof Error ? erro.message : 'Canal de eventos interrompido.' })) });
  })().catch(erro => { alterar(e => ({ ...e, carregando: false, erro: erro instanceof Error ? erro.message : 'Não foi possível carregar as conversas.' })); throw erro; }).finally(() => { iniciando = null; });
  return iniciando;
}
export function encerrarProjetos() { controladorGeral?.abort(); controladorGeral = null; for (const c of controladoresConversa.values()) c.abort(); controladoresConversa.clear(); }

export function progressoExecucao(x: Execucao, _agora: number) { return x.progresso; }
export function passosDaExecucao(x: Execucao, _agora: number): PassoTrabalho[] { return x.roteiro; }
export const execucoesDoAgente = (e: EstadoProjetos, agenteId: string) => e.execucoes.filter(x => x.agenteId === agenteId).sort((a, b) => a.inicio - b.inicio);
export interface EstadoAgente { status: Status; progresso: number; rotulo: string; nascido: boolean; execucao?: Execucao }
export function estadoAgente(e: EstadoProjetos, agenteId: string, _agora: number): EstadoAgente {
  const ag = e.agentes[agenteId]; if (!ag) return { status: 'aguardando', progresso: 0, rotulo: '', nascido: false };
  const xs = execucoesDoAgente(e, agenteId); const atual = [...xs].reverse().find(x => x.status === 'executando') ?? xs.at(-1);
  if (!atual) return { status: ag.status, progresso: ag.status === 'concluido' ? 100 : 0, rotulo: ag.avulso ? 'Disponível' : ag.espera, nascido: true };
  const status: Status = atual.status === 'executando' ? 'trabalhando' : atual.status === 'concluida' ? 'concluido' : atual.status === 'falhou' ? 'erro' : 'aguardando';
  return { status, progresso: atual.progresso, rotulo: status === 'trabalhando' ? ag.verbo : status === 'concluido' ? 'Concluído' : status === 'erro' ? 'Erro' : ag.espera, nascido: true, execucao: atual };
}
export interface EstadoDoProjeto { fase: FaseProjeto; nascidos: number; concluidos: number; pulso: number; progresso: number }
export function estadoProjeto(e: EstadoProjetos, p: ProjetoSora, agora: number): EstadoDoProjeto {
  const agentes = p.agenteIds.map(id => estadoAgente(e, id, agora)); const concluidos = agentes.filter(a => a.status === 'concluido').length;
  const progresso = p.tarefas.length ? Math.round(p.tarefas.reduce((n, t) => n + (t.progresso ?? 0), 0) / p.tarefas.length) : 0;
  const fase: FaseProjeto = p.aprovadoEm ? 'aprovado' : p.erro || p.cadeiaStatus === 'falhou' ? 'erro' : p.cadeiaStatus === 'concluida' ? 'pronto'
    : p.cadeiaStatus === 'executando' || p.cadeiaStatus === 'verificando' ? 'coordenando' : p.cadeiaStatus === 'planejando' || p.roteamento === 'cadeia' ? 'planejando' : p.mensagensPendentes ? 'pensando' : 'conversa';
  return { fase, nascidos: p.agenteIds.length, concluidos, pulso: p.agenteIds.length + concluidos + (fase === 'pronto' ? 1 : 0), progresso: fase === 'pronto' || fase === 'aprovado' ? 100 : progresso };
}

export const projetoAtivo = (e: EstadoProjetos) => e.projetos.find(p => p.id === e.projetoAtivoId) ?? null;
export const agentesDoProjeto = (e: EstadoProjetos, p: ProjetoSora | null, _agora: number) => p ? p.agenteIds.map(id => e.agentes[id]).filter((a): a is AgenteSora => !!a) : [];
export const agentesAvulsos = (e: EstadoProjetos) => Object.values(e.agentes).filter(a => a.avulso).sort((a, b) => b.criadoEm - a.criadoEm);
export const todosAgentes = (e: EstadoProjetos, _agora: number) => Object.values(e.agentes).sort((a, b) => b.criadoEm - a.criadoEm);
export function mensagensDa(e: EstadoProjetos, conversaOuAgenteId: string, _agora: number) {
  const ag = e.agentes[conversaOuAgenteId]; const conversaId = ag?.conversaId;
  return e.mensagens.filter(m => m.conversaId === conversaOuAgenteId || (!!conversaId && m.conversaId === conversaId) || m.agenteId === conversaOuAgenteId || m.autor === conversaOuAgenteId).sort((a, b) => a.criadoEm - b.criadoEm);
}
export const passosDoAgente = (e: EstadoProjetos, agenteId: string, agora: number) => execucoesDoAgente(e, agenteId).flatMap(x => passosDaExecucao(x, agora));

export function novoChat() { alterar(e => ({ ...e, projetoAtivoId: null })); }
export function abrirProjeto(id: string) { alterar(e => ({ ...e, projetoAtivoId: id })); acompanharConversa(id); }

async function idsDosAnexos(anexos: Anexo[] = []): Promise<string[]> {
  const remotos = await Promise.all(anexos.map(a => { if (!a.arquivo) throw new Error(`O arquivo ${a.nome} precisa ser selecionado novamente.`); return enviarAnexo(a.arquivo); }));
  return remotos.map(a => a.anexo_id);
}

export async function criarProjeto(pedido: string, _agora?: number, opcoes: { tipo?: 'chat' | 'projeto'; anexos?: Anexo[] } = {}): Promise<ProjetoSora> {
  const conversa = await api.post<ConversaApi>('/v1/conversas', { agente_id: null, texto: pedido, anexos: await idsDosAnexos(opcoes.anexos) });
  const projeto = projetoDaApi(conversa); projeto.pedido = pedido; projeto.mensagensPendentes = true;
  const mensagens = await api.get<MensagemApi[]>(`/v1/conversas/${conversa.id}/mensagens`);
  alterar(e => ({ ...e, projetos: [projeto, ...e.projetos.filter(p => p.id !== projeto.id)], projetoAtivoId: projeto.id, mensagens: [...e.mensagens.filter(m => m.conversaId !== conversa.id), ...mensagens.map(mensagemDaApi)] }));
  acompanharConversa(projeto.id); return projeto;
}
export async function criarAgenteIndependente(pedido: string, _agora?: number, anexos: Anexo[] = []): Promise<AgenteSora> {
  const agenteApi = await api.post<AgenteApi>('/v1/agentes', { descricao: pedido });
  const conversa = await api.post<ConversaApi>('/v1/conversas', { agente_id: agenteApi.id, texto: pedido, anexos: await idsDosAnexos(anexos) });
  const mensagens = await api.get<MensagemApi[]>(`/v1/conversas/${conversa.id}/mensagens`);
  const agente = { ...agenteDaApi(agenteApi), conversaId: conversa.id };
  alterar(e => ({ ...e, agentes: { ...e.agentes, [agente.id]: agente }, mensagens: [...e.mensagens.filter(m => m.conversaId !== conversa.id), ...mensagens.map(mensagemDaApi)] }));
  acompanharConversa(conversa.id); return agente;
}
export async function conversarComSora(texto: string, _agora?: number, anexos: Anexo[] = []): Promise<ProjetoSora> {
  const p = projetoAtivo(estado); if (!p) return criarProjeto(texto, undefined, { tipo: 'chat', anexos });
  const aceita = await api.post<{ mensagem_id: string }>(`/v1/conversas/${p.id}/mensagens`, { texto, anexos: await idsDosAnexos(anexos) });
  alterar(e => ({ ...e, mensagens: [...e.mensagens, { id: aceita.mensagem_id, conversaId: p.id, autor: 'usuario', texto, criadoEm: Date.now(), anexos: [], gerando: false }] })); acompanharConversa(p.id); return p;
}
export async function enviarParaAgente(agenteId: string, texto: string, _agora?: number, _registrar = true, anexos: Anexo[] = []) {
  const agente = estado.agentes[agenteId]; if (!agente) return; const projeto = estado.projetos.find(p => p.agenteIds.includes(agenteId));
  const conversaId = agente.conversaId ?? projeto?.id; if (!conversaId) return;
  const aceita = await api.post<{ mensagem_id: string }>(`/v1/conversas/${conversaId}/mensagens`, { texto, anexos: await idsDosAnexos(anexos), para_agente_id: projeto ? agenteId : null });
  alterar(e => ({ ...e, mensagens: [...e.mensagens, { id: aceita.mensagem_id, conversaId, agenteId, autor: 'usuario', texto, criadoEm: Date.now(), gerando: false }] })); acompanharConversa(conversaId);
}
export async function pedirAjuste(projetoId: string, texto: string, agenteId?: string) { await api.post<void>(`/v1/conversas/${projetoId}/ajuste`, { texto, agente_id: agenteId ?? null }); acompanharConversa(projetoId); }
export async function aprovarProjeto(id: string) { const p = estado.projetos.find(x => x.id === id); if (p) await api.post<void>(`/v1/conversas/${id}/aprovar`, { versao: p.versao }); }
export function renomearProjeto(id: string, titulo: string) { const limpo = titulo.trim(); if (!limpo) return; alterar(e => ({ ...e, projetos: e.projetos.map(p => p.id === id ? { ...p, titulo: limpo } : p) })); void api.patch(`/v1/conversas/${id}`, { titulo: limpo }).catch(() => void iniciarProjetos()); }

export type Desfazer = () => void;
export function removerProjeto(id: string, opcoes: { manterAgentes?: boolean } = {}): Desfazer {
  const antes = estado; alterar(e => ({ ...e, projetos: e.projetos.filter(p => p.id !== id), projetoAtivoId: e.projetoAtivoId === id ? null : e.projetoAtivoId }));
  void api.delete(`/v1/conversas/${id}?manter_agentes=${opcoes.manterAgentes ? 'true' : 'false'}`).catch(() => definir(antes)); return () => { definir(antes); void iniciarProjetos(); };
}
export async function salvarAgente(dados: RascunhoAgente & { id?: string }): Promise<AgenteSora> {
  const corpo = { nome: dados.nome, funcao: dados.funcao, papel: dados.instrucoes, cor: dados.cor, movimento: dados.tipoMovimento, ferramentas: dados.ferramentas };
  const saida = dados.id ? await api.patch<AgenteApi>(`/v1/agentes/${dados.id}`, corpo) : await api.post<AgenteApi>('/v1/agentes', corpo);
  const agente = { ...agenteDaApi(saida), ferramentas: dados.ferramentas, instrucoes: dados.instrucoes }; alterar(e => ({ ...e, agentes: { ...e.agentes, [agente.id]: { ...e.agentes[agente.id], ...agente } } })); return agente;
}
export function atualizarAgente(id: string, patch: Partial<Omit<AgenteSora, 'id'>>) { const atual = estado.agentes[id]; if (!atual) return; alterar(e => ({ ...e, agentes: { ...e.agentes, [id]: { ...atual, ...patch } } })); void api.patch(`/v1/agentes/${id}`, { nome: patch.nome, funcao: patch.funcao, papel: patch.instrucoes, cor: patch.cor, movimento: patch.tipoMovimento }).catch(() => void iniciarProjetos()); }
export function removerAgente(id: string): Desfazer { const antes = estado; alterar(e => { const agentes = { ...e.agentes }; delete agentes[id]; return { ...e, agentes }; }); void api.delete(`/v1/agentes/${id}`).catch(() => definir(antes)); return () => { definir(antes); void iniciarProjetos(); }; }

export function capturarSnapshot() { return estado; }
export function restaurarSnapshot(snapshot: EstadoProjetos) { definir(snapshot); }
export function atualizarSora(patch: Partial<SoraPerfil>) { alterar(e => ({ ...e, sora: { ...e.sora, ...patch } })); }
export function restaurarSora() { atualizarSora({ nome: 'Sora', cor: COR_SORA }); }
export function limparTudo() { definir({ ...inicial(), carregando: false }); }
export function alternarPlugin(_nome: string) { /* plugins seguem congelados */ }

export interface TextoVisivel { texto: string; gerando: boolean; interrompida: boolean }
export const duracaoStream = (_texto: string) => 0;
export function textoVisivel(m: MensagemChat, _agora: number): TextoVisivel { return { texto: m.texto, gerando: !!m.gerando, interrompida: m.interrompidaEm !== undefined }; }
export function gerandoNa(e: EstadoProjetos, conversaOuAgenteId: string, agora: number) { return mensagensDa(e, conversaOuAgenteId, agora).some(m => m.gerando); }
export function pararGeracao(conversaOuAgenteId: string) { const p = estado.projetos.find(x => x.id === conversaOuAgenteId); if (p?.cadeiaId) void api.post(`/v1/cadeias/${p.cadeiaId}/cancelar`); }
export function avaliarMensagem(id: string, valor: 'positiva' | 'negativa') { alterar(e => ({ ...e, mensagens: e.mensagens.map(m => m.id === id ? { ...m, avaliacao: m.avaliacao === valor ? undefined : valor } : m) })); }
export const podeRefazer = (_m: MensagemChat) => false;
export function refazerResposta(_id: string) { /* o backend não expõe refazer nesta fase */ }
export function podeEditar(_e: EstadoProjetos, _m: MensagemChat) { return false; }
export function editarPergunta(_id: string, _novoTexto: string) { /* edição não faz parte do contrato HTTP */ }
const previasDaSessao = new Map<string, string>();
export const previaDoAnexo = (id: string) => previasDaSessao.get(id);
export async function anexarEnvio<T>(anexos: Anexo[] | undefined, enviar: (anexos: Anexo[]) => Promise<T>): Promise<T> { (anexos ?? []).forEach(a => { if (a.urlPrevia) previasDaSessao.set(a.id, a.urlPrevia); }); return enviar(anexos ?? []); }

if (import.meta.env.DEV && typeof window !== 'undefined') (window as unknown as Record<string, unknown>).__sora = { limparTudo, lerEstado, novoChat, abrirProjeto, iniciarProjetos };
export function _aplicarEventoParaTestes(evento: EventoSse) { receber(evento); }
export function _reiniciarProjetosParaTestes() { encerrarProjetos(); estado = { ...inicial(), carregando: false }; notificar(); }
export function _definirEstadoParaTestes(snapshot: EstadoProjetos) { estado = snapshot; notificar(); }
