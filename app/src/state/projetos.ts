// Estado real de conversas, equipes e trabalho. A API hidrata o estado e os eventos SSE são
// a única fonte das transições ao vivo. O relógio serve apenas para mostrar duração na interface.
import { ferramentasParaSalvar } from '../data/ferramentas';
import { useEffect, useSyncExternalStore } from 'react';
import { api, ErroApi } from '../api/cliente';
import { acompanharEventos, type EventoSse } from '../api/eventos';
import { receberEventoEquipe } from './equipe';
import { receberEventoGrupos } from './grupos';
import { receberEventoBots } from './bots';
import { receberEventoAtencao } from './atencao';
import { receberEventoSora } from './sora';
import { enviarAnexo } from '../api/anexos';
import type { Anexo } from '../components/anexos';
import type { Movimento, PassoTrabalho, Status } from '../types';
import { aplicarEvento, registrarEnvioDoUsuario } from './aplicarEvento';

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
  /** resposta direta: a triagem já confirmou o pedido e a resposta do agente ainda não começou (instante do roteamento) */
  aguardaRespostaDesde?: number;
}
export interface FonteMensagem { n: number; titulo: string; url: string; dominio: string }
export interface MensagemChat {
  id: string; conversaId: string; autor: 'usuario' | 'sora' | string; agenteId?: string; texto: string; criadoEm: number;
  envio?: 'enviando' | 'erro';
  fontes?: FonteMensagem[]; estado?: 'concluida' | 'interrompida';
  gerando?: boolean; /** prévia ao vivo (mensagem.token): nunca persistida, some quando a mensagem oficial chega */ previa?: boolean; interrompidaEm?: number; avaliacao?: 'positiva' | 'negativa'; origem?: 'conversa'; variante?: number; anexos?: AnexoMsg[];
}
export interface AnexoMsg { id: string; nome: string; tipo: string; tamanho: number }
export interface SoraPerfil { nome: string; cor: string }
export interface EstadoProjetos {
  versao: 2; sora: SoraPerfil; agentes: Record<string, AgenteSora>; projetos: ProjetoSora[]; projetoAtivoId: string | null;
  execucoes: Execucao[]; mensagens: MensagemChat[]; pluginsConectados: string[]; carregando: boolean; erro?: string;
  historicos?: Record<string, { carregando: boolean; carregado: boolean; anteriores: boolean; erro?: string; cursor?: string; ultimo?: number }>;
  erroEventos?: string;
  mensagensOcultas?: string[];
  conversasOcupadas?: string[];
  pendencias?: Pendencia[];
  /** fluxos de prévia já encerrados: token atrasado não ressuscita a bolha */
  fluxosFechados?: string[];
}
import type { PropostaInstrucoes } from '../components/pendencias/proposta';
export type { PropostaInstrucoes };
/** Algo que a equipe espera do usuário: pergunta (inclui o orçamento estourado: Continuar/Parar) ou aprovação. */
export type Pendencia = (
  | { tipo: 'pergunta'; texto: string; opcoes: { rotulo: string; valor: string }[]; respostaLivre: boolean }
  | { tipo: 'aprovacao'; resumo: string; dano: string; quemRecebe: string | null; expiraEm: number; revisaoDominio?: RevisaoDominio; proposta?: PropostaInstrucoes }
) & { id: string; conversaId: string; desde: number; enviando?: boolean; erro?: string };
/** Cartão `aprovar_dominio` (Leme): o agente quer abrir um domínio novo num perfil com login salvo. */
export interface RevisaoDominio { dominio: string; url: string; perfil: { tipo: string; nome: string | null }; agenteId: string | null; opcoes: { rotulo: string; valor: 'sempre_permitir' | 'negar' }[] }
export type FaseProjeto = 'pensando' | 'conversa' | 'planejando' | 'coordenando' | 'pronto' | 'aprovado' | 'erro';

interface ConversaApi { id: string; agente_id: string; tipo: 'chat' | 'projeto' | 'agente'; titulo: string | null; aprovada_versao: number | null; criada_em: string; atualizada_em: string }
interface AgenteApi { id: string; tipo: 'sora' | 'individual' | 'especialista'; nome: string; funcao: string; cor: string; movimento: Movimento; status?: Status | null; estado?: 'livre' | 'trabalhando' | 'precisa_de_voce'; ferramentas?: string[] }
interface MensagemApi { id: string; conversa_id: string; autor: 'usuario' | 'sora' | 'agente' | 'sistema'; agente_id?: string | null; conteudo: string; anexos: (AnexoMsg | string)[]; criada_em: string; estado?: 'concluida' | 'interrompida'; fontes?: FonteMensagem[]; avaliacao?: 1 | -1 | null }
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
  return { id: a.id, projetoId: '', nome: a.nome, funcao: a.funcao, cor: a.cor, tipoMovimento: a.movimento, ferramentas: a.ferramentas ?? [], status: a.estado === 'trabalhando' ? 'trabalhando' : a.status ?? 'aguardando', verbo: verboPara(a.funcao), espera: a.estado === 'precisa_de_voce' ? 'Precisa de você' : 'Aguardando', instrucoes: '', avulso: a.tipo === 'individual', criadoEm: Date.now() };
}
function projetoDaApi(c: ConversaApi): ProjetoSora {
  const criadoEm = Date.parse(c.criada_em);
  return { id: c.id, tipo: c.tipo === 'projeto' ? 'projeto' : 'chat', titulo: c.titulo || 'Nova conversa', pedido: '', modelo: '', assunto: c.titulo || '', resposta: '', criadoEm, tarefas: [], agenteIds: [], entregas: {}, // fim = 0: só um evento ao vivo (cadeia.atualizada concluída) marca o fim; projeto carregado do servidor não é "acabou de terminar".
    marcos: { plano: criadoEm, nascimentos: [], trabalho: criadoEm, fim: 0 }, aprovadoEm: c.aprovada_versao ? Date.parse(c.atualizada_em) : undefined, aprovadaVersao: c.aprovada_versao, versao: 1 };
}
export function normalizarAnexos(anexos: (AnexoMsg | string)[] = []): AnexoMsg[] { return anexos.map(a => typeof a === 'string' ? { id: a, nome: 'Arquivo', tipo: '', tamanho: 0 } : a); }
function mensagemDaApi(m: MensagemApi): MensagemChat {
  const autor = m.autor === 'agente' && m.agente_id ? m.agente_id : m.autor === 'usuario' ? 'usuario' : 'sora';
  return { id: m.id, conversaId: m.conversa_id, autor, agenteId: m.agente_id ?? undefined, texto: m.conteudo, criadoEm: Date.parse(m.criada_em), anexos: normalizarAnexos(m.anexos), gerando: false, estado: m.estado, fontes: m.fontes, avaliacao: m.avaliacao === 1 ? 'positiva' : m.avaliacao === -1 ? 'negativa' : undefined };
}

let controladorGeral: AbortController | null = null;
const controladoresConversa = new Map<string, AbortController>();
const errosEventosPorCanal = new Map<string, string>();
const enviosAgenteEmVoo = new Map<string, Promise<void>>();
let iniciando: Promise<void> | null = null;
let geracaoSessao = 0;

// Prévias (`mensagem.token`) chegam em rajada: junta por fluxo e aplica uma vez por quadro. O `fim` descarrega antes.
const tokensPendentes = new Map<string, EventoSse>();
let quadroTokens: number | undefined;
function aplicarToken(evento: EventoSse) {
  if (evento.dados.canal_id) receberEventoGrupos(evento);
  else alterar(e => aplicarEvento(e, evento));
}
function descarregarTokens() {
  if (quadroTokens !== undefined && typeof cancelAnimationFrame !== 'undefined') cancelAnimationFrame(quadroTokens);
  quadroTokens = undefined;
  const lote = [...tokensPendentes.values()]; tokensPendentes.clear();
  lote.forEach(aplicarToken);
}
function receberToken(evento: EventoSse) {
  if (evento.dados.fim === true || typeof requestAnimationFrame === 'undefined') { tokensPendentes.delete(String(evento.dados.fluxo_id ?? '')); descarregarTokens(); aplicarToken(evento); return; }
  tokensPendentes.set(String(evento.dados.fluxo_id ?? ''), evento);
  quadroTokens ??= requestAnimationFrame(descarregarTokens);
}

function receber(evento: EventoSse) {
  if (evento.tipo === 'mensagem.token') { receberToken(evento); return; }
  receberEventoEquipe(evento);
  receberEventoGrupos(evento);
  receberEventoSora(evento);
  receberEventoBots(evento);
  receberEventoAtencao(evento);
  const conversaId = String(evento.dados.conversa_id ?? '');
  if (conversaId && !estado.projetos.some(p => p.id === conversaId) && !Object.values(estado.agentes).some(a => a.conversaId === conversaId)) return;
  alterar(e => aplicarEvento(e, evento));
  if (evento.tipo === 'entrega' || (evento.tipo === 'cadeia.atualizada' && evento.dados.status === 'concluida')) {
    if (conversaId) void carregarEntregas(conversaId).catch(() => undefined);
  }
}

function mensagemDoErroEventos(erro: unknown): string {
  if (erro instanceof ErroApi && erro.status === 429) {
    return 'Há muitas abas ou recargas abertas. Feche outras abas e aguarde um minuto; a Sora tentará reconectar.';
  }
  return erro instanceof Error ? erro.message : 'Canal de eventos interrompido.';
}

function definirErroEventos(canal: string, erro?: unknown) {
  if (erro === undefined) errosEventosPorCanal.delete(canal);
  else errosEventosPorCanal.set(canal, mensagemDoErroEventos(erro));
  const mensagem = errosEventosPorCanal.values().next().value as string | undefined;
  alterar(e => e.erroEventos === mensagem ? e : { ...e, erroEventos: mensagem });
}

const mapaDeEntregas = (lista: EntregasApi['entregas']): Record<string, EntregaGerada> => Object.fromEntries(lista.map(x => [x.agente_id || x.id, { ...x, agenteId: x.agente_id ?? undefined, conteudo: x.conteudo, ...(typeof x.conteudo === 'object' && x.conteudo ? x.conteudo as object : {}) } as EntregaGerada]));

async function carregarEntregas(conversaId: string): Promise<void> {
  const dados = await api.get<EntregasApi>(`/v1/conversas/${conversaId}/entregas`);
  // Versão anterior (ajuste): serve para a comparação. A nova versão só traz quem foi ajustado, então
  // quem não mudou continua com a entrega da versão anterior.
  const anterior = dados.versoes.length > 1 ? await api.get<EntregasApi>(`/v1/conversas/${conversaId}/entregas?versao=${dados.versoes.at(-2)}`).catch(() => null) : null;
  alterar(e => ({ ...e, projetos: e.projetos.map(p => {
    if (p.id !== conversaId) return p;
    const anteriores = anterior ? mapaDeEntregas(anterior.entregas) : undefined;
    const entregas = { ...(anteriores ?? {}), ...mapaDeEntregas(dados.entregas) };
    return { ...p, entregas, entregasAnteriores: anteriores, versao: dados.versoes.at(-1) ?? p.versao };
  }) }));
}

/** Comparação "versão anterior × nova": o agente cuja entrega mudou no último ajuste. */
export function comparacaoDeVersao(e: EstadoProjetos, p: ProjetoSora): { agente: AgenteSora; antes: EntregaGerada; depois: EntregaGerada } | null {
  if (p.versao < 2 || !p.entregasAnteriores) return null;
  for (const id of p.agenteIds) {
    const antes = p.entregasAnteriores[id], depois = p.entregas[id], agente = e.agentes[id];
    if (agente && antes && depois && antes.id !== depois.id) return { agente, antes, depois };
  }
  return null;
}

export function acompanharConversa(conversaId: string): void {
  if (!conversaId || controladoresConversa.has(conversaId)) return;
  for (const [id, ativo] of controladoresConversa) {
    if (id !== conversaId) { ativo.abort(); controladoresConversa.delete(id); definirErroEventos(`conversa:${id}`); }
  }
  const controlador = new AbortController(); controladoresConversa.set(conversaId, controlador);
  const canal = `conversa:${conversaId}`;
  void acompanharEventos(`/v1/conversas/${conversaId}/eventos`, {
    signal: controlador.signal,
    aoEvento: evento => receber({ ...evento, dados: { conversa_id: conversaId, ...evento.dados } }),
    aoConectar: () => definirErroEventos(canal),
    aoErro: erro => definirErroEventos(canal, erro),
  }).finally(() => {
    if (controladoresConversa.get(conversaId) === controlador) {
      controladoresConversa.delete(conversaId);
      definirErroEventos(canal);
    }
  });
}

export function iniciarProjetos(): Promise<void> {
  if (iniciando) return iniciando;
  iniciando = (async () => {
    const [conversas, agentes] = await Promise.all([api.get<ConversaApi[]>('/v1/conversas'), api.get<AgenteApi[]>('/v1/agentes')]);
    const mapa = Object.fromEntries(agentes.filter(a => a.tipo !== 'sora').map(a => [a.id, agenteDaApi(a)]));
    for (const c of conversas) { const ag = mapa[c.agente_id]; if (ag && c.tipo === 'agente') ag.conversaId = c.id; }
    const projetos = conversas.filter(c => c.tipo !== 'agente').map(c => ({ ...projetoDaApi(c), ...estado.projetos.find(p => p.id === c.id) }));
    for (const p of estado.projetos) if (!projetos.some(x => x.id === p.id)) projetos.push(p);
    definir({ ...estado, carregando: false, erro: undefined, agentes: { ...estado.agentes, ...mapa }, projetos });
    controladorGeral?.abort(); controladorGeral = new AbortController();
    void acompanharEventos('/v1/eventos', {
      signal: controladorGeral.signal,
      aoEvento: receber,
      aoConectar: () => definirErroEventos('geral'),
      aoErro: erro => definirErroEventos('geral', erro),
    });
  })().catch(erro => { alterar(e => ({ ...e, carregando: false, erro: erro instanceof Error ? erro.message : 'Não foi possível carregar as conversas.' })); throw erro; }).finally(() => { iniciando = null; });
  return iniciando;
}
export function encerrarProjetos() {
  geracaoSessao++;
  tokensPendentes.clear(); cargas.clear(); tentativas.clear(); enviosAgenteEmVoo.clear(); conversasCriadas.clear();
  controladorGeral?.abort(); controladorGeral = null;
  encerrarConversas(); errosEventosPorCanal.clear();
}

function encerrarConversa(conversaId: string) {
  controladoresConversa.get(conversaId)?.abort();
  controladoresConversa.delete(conversaId);
  definirErroEventos(`conversa:${conversaId}`);
}

function encerrarConversas() {
  for (const id of [...controladoresConversa.keys()]) encerrarConversa(id);
}

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
  const id = 'local-' + crypto.randomUUID();
  const projeto = projetoDaApi({ id, agente_id: '', tipo: opcoes.tipo ?? 'chat', titulo: pedido.slice(0, 80), aprovada_versao: null, criada_em: new Date().toISOString(), atualizada_em: new Date().toISOString() });
  alterar(e => ({ ...e, projetos: [projeto, ...e.projetos], projetoAtivoId: id }));
  await enviarOtimista(id, pedido, opcoes.anexos ?? [], undefined, true);
  return projetoAtivo(estado) ?? projeto;
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
  await enviarOtimista(p.id, texto, anexos, undefined, p.id.startsWith('local-'));
  return projetoAtivo(estado) ?? p;
}
export async function enviarParaAgente(agenteId: string, texto: string, _agora?: number, _registrar = true, anexos: Anexo[] = []) {
  const agente = estado.agentes[agenteId];
  if (!agente) throw new Error('Bot não encontrado.');
  return enviarOtimista(agente.conversaId ?? agenteId, texto, anexos, agenteId, !agente.conversaId);
}

// A bolha nasce antes de qualquer await (incluindo upload e fila de envio).
const conversasCriadas = new Map<string, string>();
const tentativas = new Map<string, () => Promise<void>>();
export async function tentarEnvioNovamente(id: string) { await tentativas.get(id)?.(); }
function enviarOtimista(conversaInicial: string, texto: string, anexos: Anexo[], agenteId?: string, criar = false): Promise<void> {
  const sessao = geracaoSessao;
  let anexosRemotos: AnexoMsg[] = anexos;
  const localId = 'local-' + crypto.randomUUID(), enviadoEm = Date.now();
  alterar(e => ({ ...e, mensagens: [...e.mensagens, { id: localId, conversaId: conversaInicial, agenteId, autor: 'usuario', texto, criadoEm: enviadoEm, anexos, envio: 'enviando' }] }));
  let conversaId = conversaInicial, aceitaId: string | undefined, criada = false, emVoo = false;
  const executar = async () => {
    if (emVoo || sessao !== geracaoSessao) return;
    emVoo = true;
    alterar(e => ({ ...e, mensagens: e.mensagens.map(m => m.id === localId ? { ...m, envio: 'enviando' } : m) }));
    try {
      const remota = conversasCriadas.get(conversaInicial);
      if (remota && !criada) { conversaId = remota; criar = false; }
      // Reconsulta depois da fila: outro envio pode ter criado a conversa do bot.
      if (agenteId && estado.agentes[agenteId]?.conversaId) { conversaId = estado.agentes[agenteId]!.conversaId!; criar = false; }
      if (!criada && !aceitaId) {
        const ids = await idsDosAnexos(anexos);
        if (sessao !== geracaoSessao) return;
        anexosRemotos = anexos.map((anexo, i) => {
          const id = ids[i]!; if (anexo.urlPrevia) previasDaSessao.set(id, anexo.urlPrevia);
          return { id, nome: anexo.nome, tipo: anexo.tipo, tamanho: anexo.tamanho };
        });
        if (criar) {
          const conversa = await api.post<ConversaApi>('/v1/conversas', { agente_id: agenteId ?? null, texto, anexos: ids });
          if (sessao !== geracaoSessao) return;
          conversaId = conversa.id; criada = true; conversasCriadas.set(conversaInicial, conversaId);
          alterar(e => ({ ...e,
            agentes: agenteId ? { ...e.agentes, [agenteId]: { ...e.agentes[agenteId]!, conversaId } } : e.agentes,
            projetos: agenteId ? e.projetos : e.projetos.map(p => p.id === conversaInicial ? projetoDaApi(conversa) : p),
            projetoAtivoId: e.projetoAtivoId === conversaInicial ? conversaId : e.projetoAtivoId,
            mensagens: e.mensagens.map(m => m.id === localId ? { ...m, conversaId } : m),
          }));
        } else {
          const aceita = await api.post<{ mensagem_id: string }>(`/v1/conversas/${conversaId}/mensagens`, { texto, anexos: ids, para_agente_id: agenteId && !estado.agentes[agenteId]?.avulso ? agenteId : null });
          if (sessao !== geracaoSessao) return;
          aceitaId = aceita.mensagem_id;
        }
      }
      if (criada && !aceitaId) {
        const mensagens = await api.get<MensagemApi[]>(`/v1/conversas/${conversaId}/mensagens`);
        if (sessao !== geracaoSessao) return;
        aceitaId = mensagens.find(m => m.autor === 'usuario' && m.conteudo === texto)?.id;
        if (!aceitaId) throw new Error('A confirmação do envio ainda não chegou.');
        alterar(e => ({ ...e, mensagens: [...e.mensagens, ...mensagens.filter(m => m.id !== aceitaId && !e.mensagens.some(x => x.id === m.id)).map(mensagemDaApi)] }));
      }
      alterar(e => registrarEnvioDoUsuario(e, { id: aceitaId!, localId, conversaId, agenteId, texto, enviadoEm, anexos: anexosRemotos }));
      tentativas.delete(localId); acompanharConversa(conversaId);
    } catch {
      if (sessao !== geracaoSessao) return;
      alterar(e => ({ ...e, mensagens: e.mensagens.map(m => m.id === localId ? { ...m, envio: 'erro' } : m) }));
    } finally { emVoo = false; }
  };
  const enfileirar = () => {
    const chave = agenteId ?? conversaInicial;
    const envio = (enviosAgenteEmVoo.get(chave) ?? Promise.resolve()).catch(() => undefined).then(executar);
    enviosAgenteEmVoo.set(chave, envio);
    return envio.finally(() => { if (enviosAgenteEmVoo.get(chave) === envio) enviosAgenteEmVoo.delete(chave); });
  };
  tentativas.set(localId, enfileirar);
  return enfileirar();
}

const cargas = new Map<string, Promise<void>>();
export function carregarMensagens(conversaId: string, anteriores = false): Promise<void> {
  if (!conversaId || conversaId.startsWith('local-')) return Promise.resolve();
  const sessao = geracaoSessao;
  const atual = estado.historicos?.[conversaId];
  if (cargas.has(conversaId)) return cargas.get(conversaId)!;
  if (!anteriores && atual?.carregado) return Promise.resolve();
  if (anteriores && (!atual?.anteriores || !atual.cursor)) return Promise.resolve();
  const inicioCarga = Date.now();
  const antes = anteriores ? atual?.cursor : undefined;
  alterar(e => ({ ...e, historicos: { ...e.historicos, [conversaId]: { carregado: false, anteriores: false, ...atual, carregando: true, erro: undefined } } }));
  const carga = api.get<MensagemApi[]>(`/v1/conversas/${conversaId}/mensagens?limite=50${antes ? '&antes=' + encodeURIComponent(antes) : ''}`).then(lista => {
    if (sessao !== geracaoSessao) return;
    alterar(e => ({ ...e,
      mensagens: [...e.mensagens.filter(m => !lista.some(x => x.id === m.id) && (anteriores || m.conversaId !== conversaId || m.envio || m.criadoEm > inicioCarga)), ...lista.map(mensagemDaApi)].sort((a,b) => a.criadoEm - b.criadoEm),
      historicos: { ...e.historicos, [conversaId]: { carregado: true, carregando: false, anteriores: lista.length === 50, ultimo: Math.max(atual?.ultimo ?? 0, ...lista.map(m => Date.parse(m.criada_em))), cursor: [...lista].sort((a,b) => a.criada_em.localeCompare(b.criada_em))[0]?.criada_em ?? antes } },
    }));
  }).catch(() => {
    if (sessao !== geracaoSessao) return;
    alterar(e => ({ ...e, historicos: { ...e.historicos, [conversaId]: { carregado: false, anteriores: false, ...atual, carregando: false, erro: 'Não foi possível carregar as mensagens.' } } }));
  }).finally(() => { if (cargas.get(conversaId) === carga) cargas.delete(conversaId); });
  cargas.set(conversaId, carga); return carga;
}
export async function pedirAjuste(projetoId: string, texto: string, agenteId?: string) { await api.post<void>(`/v1/conversas/${projetoId}/ajuste`, { texto, agente_id: agenteId ?? null }); acompanharConversa(projetoId); }
export async function aprovarProjeto(id: string) { const p = estado.projetos.find(x => x.id === id); if (p) await api.post<void>(`/v1/conversas/${id}/aprovar`, { versao: p.versao }); }
export const pendenciasDa = (e: EstadoProjetos, conversaId: string | null | undefined): Pendencia[] => conversaId ? (e.pendencias ?? []).filter(p => p.conversaId === conversaId) : [];
const semPendencia = (id: string) => (e: EstadoProjetos): EstadoProjetos => ({ ...e, pendencias: (e.pendencias ?? []).filter(p => p.id !== id) });
const marcarPendencia = (id: string, patch: Partial<Pick<Pendencia, 'enviando' | 'erro'>>) => (e: EstadoProjetos): EstadoProjetos => ({ ...e, pendencias: (e.pendencias ?? []).map(p => p.id === id ? { ...p, ...patch } : p) });
async function enviarPendencia(id: string, chamada: () => Promise<unknown>) {
  alterar(marcarPendencia(id, { enviando: true, erro: undefined }));
  try { await chamada(); alterar(semPendencia(id)); }
  catch (erro) {
    // 404/409: já respondida ou vencida em outro lugar; o cartão não tem mais o que fazer
    if (erro instanceof ErroApi && (erro.status === 404 || erro.status === 409)) { alterar(semPendencia(id)); return; }
    alterar(marcarPendencia(id, { enviando: false, erro: erro instanceof Error ? erro.message : 'Não foi possível enviar. Tente de novo.' }));
  }
}
export const responderPergunta = (id: string, valor: string) => enviarPendencia(id, () => api.post<void>(`/v1/perguntas/${id}/responder`, { valor }));
export type DecisaoDeAprovacao = 'permitir_uma_vez' | 'sempre_permitir' | 'negar';
export const decidirAprovacao = (id: string, decisao: DecisaoDeAprovacao) => enviarPendencia(id, () => api.post<void>(`/v1/aprovacoes/${id}/decidir`, { decisao }));
export function renomearProjeto(id: string, titulo: string) { const limpo = titulo.trim(); if (!limpo) return; alterar(e => ({ ...e, projetos: e.projetos.map(p => p.id === id ? { ...p, titulo: limpo } : p) })); void api.patch(`/v1/conversas/${id}`, { titulo: limpo }).catch(() => void iniciarProjetos()); }

export type Desfazer = () => void;
export function removerProjeto(id: string, opcoes: { manterAgentes?: boolean } = {}): Desfazer {
  encerrarConversa(id);
  const antes = estado; alterar(e => ({ ...e, projetos: e.projetos.filter(p => p.id !== id), projetoAtivoId: e.projetoAtivoId === id ? null : e.projetoAtivoId }));
  void api.delete(`/v1/conversas/${id}?manter_agentes=${opcoes.manterAgentes ? 'true' : 'false'}`).catch(() => definir(antes)); return () => { definir(antes); void iniciarProjetos(); };
}
export async function salvarAgente(dados: RascunhoAgente & { id?: string }): Promise<AgenteSora> {
  const corpo = { nome: dados.nome, funcao: dados.funcao, papel: dados.instrucoes, cor: dados.cor, movimento: dados.tipoMovimento, ferramentas: ferramentasParaSalvar(dados.ferramentas) };
  const saida = dados.id ? await api.patch<AgenteApi>(`/v1/agentes/${dados.id}`, corpo) : await api.post<AgenteApi>('/v1/agentes', corpo);
  const agente = { ...agenteDaApi(saida), ferramentas: dados.ferramentas, instrucoes: dados.instrucoes }; alterar(e => ({ ...e, agentes: { ...e.agentes, [agente.id]: { ...e.agentes[agente.id], ...agente } } })); return agente;
}
export function atualizarAgente(id: string, patch: Partial<Omit<AgenteSora, 'id'>>) { const atual = estado.agentes[id]; if (!atual) return; alterar(e => ({ ...e, agentes: { ...e.agentes, [id]: { ...atual, ...patch } } })); void api.patch(`/v1/agentes/${id}`, { nome: patch.nome, funcao: patch.funcao, papel: patch.instrucoes, cor: patch.cor, movimento: patch.tipoMovimento }).catch(() => void iniciarProjetos()); }
export function removerAgente(id: string): Desfazer { const antes = estado; alterar(e => { const agentes = { ...e.agentes }; delete agentes[id]; return { ...e, agentes }; }); void api.delete(`/v1/agentes/${id}`).catch(() => definir(antes)); return () => { definir(antes); void iniciarProjetos(); }; }

export function capturarSnapshot() { return estado; }
export function restaurarSnapshot(snapshot: EstadoProjetos) { definir(snapshot); }
export function atualizarSora(patch: Partial<SoraPerfil>) { alterar(e => ({ ...e, sora: { ...e.sora, ...patch } })); }
export function restaurarSora() { atualizarSora({ nome: 'Sora', cor: COR_SORA }); }
export async function limparTudo() {
  encerrarConversas();
  const conversas = new Set([
    ...estado.projetos.map(projeto => projeto.id),
    ...Object.values(estado.agentes).map(agente => agente.conversaId).filter((id): id is string => !!id),
  ]);
  const individuais = Object.values(estado.agentes).filter(agente => agente.avulso).map(agente => agente.id);
  try {
    for (const conversaId of conversas) {
      await api.delete(`/v1/conversas/${conversaId}?manter_agentes=false`);
    }
    for (const agenteId of individuais) await api.delete(`/v1/agentes/${agenteId}`);
    definir({ ...inicial(), carregando: false });
  } catch (erro) {
    await iniciarProjetos().catch(() => undefined);
    throw erro;
  }
}
export function alternarPlugin(_nome: string) { /* plugins seguem congelados */ }

export interface TextoVisivel { texto: string; gerando: boolean; interrompida: boolean }
export const duracaoStream = (_texto: string) => 0;
export function textoVisivel(m: MensagemChat, _agora: number): TextoVisivel { return { texto: m.texto, gerando: !!m.gerando, interrompida: m.estado === 'interrompida' || m.interrompidaEm !== undefined }; }
/** Depois da confirmação da triagem, quanto tempo a conversa segue "pensando" à espera da resposta do agente. */
const ESPERA_RESPOSTA_DIRETA_MS = 120_000;
export function gerandoNa(e: EstadoProjetos, conversaOuAgenteId: string, agora: number) {
  const id = e.agentes[conversaOuAgenteId]?.conversaId ?? conversaOuAgenteId;
  const p = e.projetos.find(x => x.id === id);
  const ultima = mensagensDa(e, conversaOuAgenteId, agora).at(-1);
  return !!(e.conversasOcupadas?.includes(id) || p?.mensagensPendentes || (!!p?.aguardaRespostaDesde && agora - p.aguardaRespostaDesde < ESPERA_RESPOSTA_DIRETA_MS) || ['planejando', 'executando', 'verificando'].includes(p?.cadeiaStatus ?? '') || ultima?.autor === 'usuario' && ultima.estado !== 'interrompida' && ultima.envio !== 'erro' || mensagensDa(e, conversaOuAgenteId, agora).some(m => m.gerando));
}
export async function pararConversa(conversaOuAgenteId: string) {
  const sessao = geracaoSessao;
  // Primeiro envio pode ainda estar criando a conversa. Espere sua confirmação antes de parar.
  await enviosAgenteEmVoo.get(conversaOuAgenteId);
  if (sessao !== geracaoSessao) return;
  const conversaId = estado.agentes[conversaOuAgenteId]?.conversaId ?? conversasCriadas.get(conversaOuAgenteId) ?? conversaOuAgenteId;
  await api.post<void>(`/v1/conversas/${conversaId}/parar`);
  receberEventoAtencao({ tipo: 'precisa_de_voce.atualizado' }); // relê a central: o servidor expira os cartões das etapas
  const lista = await api.get<MensagemApi[]>(`/v1/conversas/${conversaId}/mensagens?limite=50`);
  if (sessao !== geracaoSessao) return;
  alterar(e => ({ ...e,
    projetos: e.projetos.map(p => p.id === conversaId ? { ...p, mensagensPendentes: false, aguardaRespostaDesde: undefined, cadeiaStatus: p.cadeiaId ? 'cancelada' : p.cadeiaStatus } : p),
    // Parar cancela a cadeia desta conversa e expira os cartões das etapas: saem do chat sem esperar o evento.
    pendencias: e.projetos.some(p => p.id === conversaId) ? (e.pendencias ?? []).filter(x => x.conversaId !== conversaId) : e.pendencias,
    mensagens: [...e.mensagens.filter(m => !lista.some(x => x.id === m.id) && !(m.previa && m.conversaId === conversaId)).map(m => m.conversaId === conversaId ? { ...m, gerando: false } : m), ...lista.map(mensagemDaApi)].sort((a,b) => a.criadoEm - b.criadoEm),
  }));
}
export async function avaliarMensagem(id: string, valor: 'positiva' | 'negativa') {
  const m = estado.mensagens.find(x => x.id === id); if (!m) return;
  const sessao = geracaoSessao;
  const resposta = await api.put<MensagemApi>(`/v1/conversas/${m.conversaId}/mensagens/${id}/avaliacao`, { valor: m.avaliacao === valor ? null : valor === 'positiva' ? 1 : -1 });
  if (sessao !== geracaoSessao) return;
  alterar(e => ({ ...e, mensagens: e.mensagens.map(x => x.id === id ? { ...x, avaliacao: mensagemDaApi(resposta).avaliacao } : x) }));
}
export function podeEditar(e: EstadoProjetos, m: MensagemChat) {
  return m.autor === 'usuario' && !m.envio && !gerandoNa(e, m.conversaId, 0) && e.mensagens.filter(x => x.conversaId === m.conversaId && x.autor === 'usuario').at(-1)?.id === m.id;
}
export const podeRefazer = (m: MensagemChat) => m.autor !== 'usuario' && !gerandoNa(estado, m.conversaId, 0) && estado.mensagens.filter(x => x.conversaId === m.conversaId).at(-1)?.id === m.id;
async function substituirTurno(id: string, novoTexto?: string) {
  const m = estado.mensagens.find(x => x.id === id); if (!m || estado.conversasOcupadas?.includes(m.conversaId)) return;
  const sessao = geracaoSessao;
  const conversa = m.conversaId;
  const antigas = estado.mensagens.filter(x => x.conversaId === conversa);
  const pergunta = antigas.filter(x => x.autor === 'usuario').at(-1);
  if (!pergunta) return;
  const ocultas = antigas.slice(antigas.indexOf(pergunta)).map(x => x.id);
  alterar(e => ({ ...e, conversasOcupadas: [...e.conversasOcupadas ?? [], conversa] }));
  try {
    const caminho = `/v1/conversas/${conversa}/mensagens/${id}`;
    if (novoTexto === undefined) await api.post(caminho + '/refazer');
    else await api.patch(caminho, { texto: novoTexto.trim() });
    if (sessao !== geracaoSessao) return;
    alterar(e => ({ ...e, mensagensOcultas: [...e.mensagensOcultas ?? [], ...ocultas], mensagens: e.mensagens.filter(x => !ocultas.includes(x.id)) }));
    const lista = await api.get<MensagemApi[]>(`/v1/conversas/${conversa}/mensagens?limite=50`);
    if (sessao !== geracaoSessao) return;
    alterar(e => ({ ...e, mensagens: [...e.mensagens.filter(x => !lista.some(y => y.id === x.id)), ...lista.map(mensagemDaApi)].sort((a,b) => a.criadoEm - b.criadoEm) }));
  } finally {
    if (sessao === geracaoSessao) alterar(e => ({ ...e, conversasOcupadas: e.conversasOcupadas?.filter(x => x !== conversa) }));
  }
}
export const refazerResposta = (id: string) => substituirTurno(id);
export const editarPergunta = (id: string, novoTexto: string) => substituirTurno(id, novoTexto);
const previasDaSessao = new Map<string, string>();
export const previaDoAnexo = (id: string) => previasDaSessao.get(id);
export async function anexarEnvio<T>(anexos: Anexo[] | undefined, enviar: (anexos: Anexo[]) => Promise<T>): Promise<T> { (anexos ?? []).forEach(a => { if (a.urlPrevia) previasDaSessao.set(a.id, a.urlPrevia); }); return enviar(anexos ?? []); }

if (import.meta.env.DEV && typeof window !== 'undefined') (window as unknown as Record<string, unknown>).__sora = { limparTudo, lerEstado, novoChat, abrirProjeto, iniciarProjetos, removerProjeto, removerAgente, injetarEvento: receber };
export function _aplicarEventoParaTestes(evento: EventoSse) { receber(evento); }
export function _reiniciarProjetosParaTestes() { encerrarProjetos(); estado = { ...inicial(), carregando: false }; notificar(); }
export function _definirEstadoParaTestes(snapshot: EstadoProjetos) { estado = snapshot; notificar(); }

export function registrarBot(agente: AgenteApi): void { alterar(e => ({ ...e, agentes: { ...e.agentes, [agente.id]: agenteDaApi(agente) } })); }
