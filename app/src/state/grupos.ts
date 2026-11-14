import { useEffect, useSyncExternalStore } from 'react';
import { enviarMensagemGrupo, grupoDaApi, listarGrupos, listarMensagensGrupo, listarTarefasGrupo, mensagemDaApi, tarefaDaApi, type EnvioMensagemGrupo, type GrupoApi, type MensagemGrupoApi, type TarefaGrupoApi } from '../api/grupos';

export interface GrupoResumo {
  id: string;
  nome: string;
  membros: string[];
  liderId?: string | null;
  precisaDeVoce: boolean;
  trabalhando: boolean;
  /** Menos de 2 bots: o servidor recusa mensagens (409) até o grupo ganhar bots. */
  precisaDeBots?: boolean;
}

interface EstadoGrupos {
  lista: GrupoResumo[];
  carregando: boolean;
  carregado: boolean;
  erro: string | null;
  mensagens: Record<string, MensagemGrupoApi[]>;
  /** Tarefas do grupo por id; o estado de cada membro (trabalhando/parado) sai daqui, ao vivo. */
  tarefas: Record<string, Record<string, TarefaGrupoApi>>;
}

export type EstadoMembro = 'livre' | 'trabalhando' | 'parado';
const ATIVAS = new Set(['na_fila', 'rodando', 'aguardando_filhas']);

/** Estado de um bot dentro do grupo a partir das tarefas abertas dele. */
export function estadoDoMembro(tarefas: Record<string, TarefaGrupoApi> | undefined, botId: string): EstadoMembro {
  const doBot = Object.values(tarefas ?? {}).filter(tarefa => tarefa.donoId === botId);
  if (doBot.some(tarefa => ATIVAS.has(tarefa.status))) return 'trabalhando';
  if (doBot.some(tarefa => tarefa.status === 'parada')) return 'parado';
  return 'livre';
}

const inicial = (): EstadoGrupos => ({ lista: [], carregando: false, carregado: false, erro: null, mensagens: {}, tarefas: {} });
let estado = inicial();
const ouvintes = new Set<() => void>();
const definir = (proximo: EstadoGrupos) => { estado = proximo; ouvintes.forEach(fn => fn()); };
const mensagem = (erro: unknown) => erro instanceof Error ? erro.message : 'Não foi possível carregar os grupos.';

export const lerGrupos = () => estado;
export function useGrupos() {
  const atual = useSyncExternalStore(fn => { ouvintes.add(fn); return () => { ouvintes.delete(fn); }; }, lerGrupos, lerGrupos);
  useEffect(() => { void carregarGrupos().catch(() => undefined); }, []);
  return atual;
}

export function receberGrupo(grupo: GrupoApi): void {
  const semAtual = estado.lista.filter(item => item.id !== grupo.id);
  definir({ ...estado, lista: [...semAtual, grupo].sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR')) });
}

export function removerGrupo(id: string): void {
  if (!estado.lista.some(item => item.id === id)) return;
  definir({ ...estado, lista: estado.lista.filter(item => item.id !== id) });
}

// Releitura pedida durante uma leitura em andamento: a resposta em voo pode já estar velha.
let releituraPendente = false;
let relerGruposEm: ReturnType<typeof setTimeout> | undefined;

export async function carregarGrupos(forcar = false): Promise<void> {
  if (estado.carregando) { if (forcar) releituraPendente = true; return; }
  if (estado.carregado && !forcar) return;
  definir({ ...estado, carregando: true, erro: null });
  try {
    const lista = await listarGrupos();
    definir({ ...estado, lista: [...lista].sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR')), carregando: false, carregado: true, erro: null });
  } catch (erro) {
    definir({ ...estado, carregando: false, carregado: true, erro: mensagem(erro) });
    throw erro;
  } finally {
    if (releituraPendente) { releituraPendente = false; void carregarGrupos(true).catch(() => undefined); }
  }
}

/** Relê GET /v1/grupos agrupando eventos próximos (~400 ms), como a atenção. */
function agendarReleituraDosGrupos(): void {
  clearTimeout(relerGruposEm);
  relerGruposEm = setTimeout(() => { void carregarGrupos(true).catch(() => undefined); }, 400);
}

function inserirMensagem(grupoId: string, mensagem: MensagemGrupoApi): void {
  const atual = estado.mensagens[grupoId] ?? [];
  const lista = [...atual.filter(item => item.id !== mensagem.id), mensagem].sort((a, b) => a.sequencia - b.sequencia);
  definir({ ...estado, mensagens: { ...estado.mensagens, [grupoId]: lista } });
}

export async function carregarMensagensDoGrupo(grupoId: string): Promise<void> {
  const atuais = estado.mensagens[grupoId] ?? [];
  const depoisDe = atuais.at(-1)?.sequencia ?? 0;
  const novas = await listarMensagensGrupo(grupoId, depoisDe);
  for (const mensagem of novas) inserirMensagem(grupoId, mensagem);
}

export async function enviarMensagemAoGrupo(grupoId: string, corpo: EnvioMensagemGrupo): Promise<void> {
  inserirMensagem(grupoId, await enviarMensagemGrupo(grupoId, corpo));
}

/** Guarda tarefas, mas nunca troca uma revisão nova por uma antiga (SSE e HTTP podem cruzar). */
export function receberTarefasDoGrupo(tarefas: TarefaGrupoApi[]): void {
  if (!tarefas.length) return;
  const proximo = { ...estado.tarefas };
  for (const tarefa of tarefas) {
    if (!tarefa.id || !tarefa.grupoId) continue;
    const doGrupo = { ...(proximo[tarefa.grupoId] ?? {}) };
    const atual = doGrupo[tarefa.id];
    if (!atual || atual.revisao <= tarefa.revisao) doGrupo[tarefa.id] = tarefa;
    proximo[tarefa.grupoId] = doGrupo;
  }
  definir({ ...estado, tarefas: proximo });
}

export async function carregarTarefasDoGrupo(grupoId: string): Promise<void> {
  receberTarefasDoGrupo(await listarTarefasGrupo(grupoId));
}

type EventoEtapa5 = { tipo: string; dados: Record<string, unknown> };
export function receberEventoGrupos(evento: EventoEtapa5): void {
  if (evento.tipo === 'canal.atualizado') {
    // Ao abrir, o SSE reentrega o histórico: aplicar cada `canal.atualizado` fazia grupos arquivados
    // e nomes/estados antigos piscarem na barra lateral. Arquivado sai na hora; o resto só agenda a
    // releitura de GET /v1/grupos, que é a verdade.
    const id = grupoDaApi(evento.dados).id;
    if (id && evento.dados.arquivado === true) removerGrupo(id);
    if (id) agendarReleituraDosGrupos();
  } else if (evento.tipo === 'canal.mensagem') {
    const mensagem = mensagemDaApi(evento.dados);
    if (mensagem.id && mensagem.grupoId) inserirMensagem(mensagem.grupoId, mensagem);
  } else if (evento.tipo === 'canal.tarefa') {
    receberTarefasDoGrupo([tarefaDaApi(evento.dados)]);
  }
  // `precisa_de_voce.atualizado` não é aplicado aqui: ao abrir, o SSE reentrega o histórico e o
  // conteúdo antigo fazia "Precisa de você" e cartões piscarem. O evento só dispara a releitura de
  // GET /v1/atencao (`receberEventoAtencao` em state/atencao.ts), que é a verdade.
}

export function _reiniciarGruposParaTestes(): void { clearTimeout(relerGruposEm); releituraPendente = false; definir(inicial()); }

const ABERTAS = new Set(['na_fila', 'rodando', 'aguardando_filhas', 'parada', 'falhou']);

/** Botões que a tarefa mostra agora: os do servidor, ou os mesmos estados que ele aceita em cada controle. */
export function acoesDaTarefa(tarefa: TarefaGrupoApi): NonNullable<TarefaGrupoApi['acoes']> {
  if (tarefa.acoes) return tarefa.acoes;
  if (tarefa.status === 'na_fila' || tarefa.status === 'rodando' || tarefa.status === 'aguardando_filhas') return ['parar'];
  if (tarefa.status === 'parada' || tarefa.status === 'falhou') return ['retomar', 'reatribuir', 'cancelar'];
  return [];
}

/** Tarefas do grupo que ainda pedem atenção (ativas, paradas ou que falharam), da mais antiga para a mais nova. */
export function tarefasAbertasDoGrupo(tarefas: Record<string, TarefaGrupoApi> | undefined): TarefaGrupoApi[] {
  return Object.values(tarefas ?? {}).filter(tarefa => ABERTAS.has(tarefa.status));
}

/** Menos de 2 bots além da Sora. Vale o campo do servidor; sem ele, conta os membros. */
export function grupoPrecisaDeBots(grupo: Pick<GrupoResumo, 'membros' | 'liderId' | 'precisaDeBots'>): boolean {
  if (typeof grupo.precisaDeBots === 'boolean') return grupo.precisaDeBots;
  const lider = grupo.liderId ?? grupo.membros[0];
  return grupo.membros.filter(id => id !== lider).length < 2;
}
