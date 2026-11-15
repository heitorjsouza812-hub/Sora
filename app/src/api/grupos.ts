import { api } from './cliente';
import { propostaDe } from '../components/pendencias/proposta';
import type { PedidoAtencao, PropostaGrupo } from '../components/pendencias/tipos';

export type EstadoMembroGrupo = 'livre' | 'trabalhando' | 'precisa_de_voce' | 'parado';

export interface GrupoApi {
  id: string;
  nome: string;
  membros: string[];
  /** A Sora, chefe de equipe (também é `membros[0]`). */
  liderId: string | null;
  precisaDeVoce: boolean;
  trabalhando: boolean;
  /** Campo opcional do backend: o grupo ficou com menos de 2 bots e não aceita mensagens até ganhar bots. */
  precisaDeBots?: boolean;
}

export interface MensagemGrupoApi {
  id: string;
  grupoId: string;
  sequencia: number;
  autor: 'usuario' | 'sora' | 'bot' | 'sistema';
  botId: string | null;
  texto: string;
  tipo: 'mensagem' | 'repasse' | 'resultado';
  respondeA: string | null;
  anexos: AnexoGrupo[];
  criadaEm: string;
}

/** Anexo de mensagem: o backend manda só o UUID; o download passa por `/v1/anexos/{id}` com token. */
export interface AnexoGrupo { id: string; nome: string }

export type StatusTarefaGrupo = 'na_fila' | 'rodando' | 'aguardando_filhas' | 'parada' | 'concluida' | 'falhou' | 'cancelada';
export type AcaoTarefaGrupo = 'parar' | 'retomar' | 'reatribuir' | 'cancelar';
export interface TarefaGrupoApi {
  id: string; grupoId: string; donoId: string; status: StatusTarefaGrupo; revisao: number;
  paiId?: string | null;
  /** Por que a tarefa está parada (ex.: aguardando_decisao). */
  motivo?: string | null;
  /** Botões que o servidor libera para a tarefa agora. */
  acoes?: AcaoTarefaGrupo[];
}

type Dados = Record<string, unknown>;
const texto = (v: unknown) => typeof v === 'string' ? v : '';
const textoOuNulo = (v: unknown) => typeof v === 'string' && v ? v : null;
const numero = (v: unknown) => typeof v === 'number' ? v : 0;
const lista = (v: unknown): unknown[] => Array.isArray(v) ? v : [];

export function grupoDaApi(d: Dados): GrupoApi {
  return {
    id: texto(d.id ?? d.grupo_id ?? d.canal_id),
    nome: texto(d.nome),
    membros: lista(d.membros).map(item => typeof item === 'string' ? item : texto((item as Dados).id ?? (item as Dados).agente_id)).filter(Boolean),
    liderId: textoOuNulo(d.lider_id),
    precisaDeVoce: d.precisa_de_voce === true || d.estado === 'precisa_de_voce',
    trabalhando: d.trabalhando === true || d.estado === 'trabalhando',
    ...(typeof d.precisa_de_bots === 'boolean' ? { precisaDeBots: d.precisa_de_bots } : {}),
  };
}

// Nomes dos arquivos que este navegador enviou; os demais aparecem como "Arquivo N" até o download.
const nomesDeAnexos = new Map<string, string>();
export const lembrarNomeDoAnexo = (id: string, nome: string) => { nomesDeAnexos.set(id, nome); };

function anexoDaApi(v: unknown, indice: number): AnexoGrupo {
  const d = (typeof v === 'string' ? { id: v } : v ?? {}) as Dados;
  const id = texto(d.id ?? d.anexo_id);
  return { id, nome: texto(d.nome) || nomesDeAnexos.get(id) || `Arquivo ${indice + 1}` };
}

const ACOES_TAREFA = new Set<string>(['parar', 'retomar', 'reatribuir', 'cancelar']);

export function tarefaDaApi(d: Dados): TarefaGrupoApi {
  return {
    id: texto(d.tarefa_id ?? d.id), grupoId: texto(d.canal_id), donoId: texto(d.dono_id), status: texto(d.status) as StatusTarefaGrupo, revisao: numero(d.revisao),
    paiId: textoOuNulo(d.pai_id), motivo: textoOuNulo(d.motivo),
    ...(Array.isArray(d.acoes) ? { acoes: d.acoes.filter((acao): acao is AcaoTarefaGrupo => typeof acao === 'string' && ACOES_TAREFA.has(acao)) } : {}),
  };
}

export function mensagemDaApi(d: Dados): MensagemGrupoApi {
  const autorBruto = texto(d.autor);
  const tipoBruto = texto(d.tipo);
  return {
    id: texto(d.id ?? d.mensagem_id),
    grupoId: texto(d.grupo_id ?? d.canal_id),
    sequencia: numero(d.sequencia ?? d.seq),
    autor: autorBruto === 'usuario' || autorBruto === 'sora' || autorBruto === 'sistema' ? autorBruto : 'bot',
    botId: textoOuNulo(d.bot_id ?? d.agente_id),
    texto: texto(d.texto),
    tipo: tipoBruto === 'repasse' || tipoBruto === 'atividade' ? 'repasse' : tipoBruto === 'resultado' ? 'resultado' : 'mensagem',
    respondeA: textoOuNulo(d.responde_a),
    anexos: lista(d.anexos).map(anexoDaApi).filter(anexo => anexo.id),
    criadaEm: texto(d.criada_em),
  };
}

// Todos os caminhos da etapa 5 ficam concentrados aqui para acompanhar o contrato da Âncora.
const RAIZ = '/v1/grupos';
const ATENCAO = '/v1/atencao';

export async function listarGrupos(): Promise<GrupoApi[]> {
  return (await api.get<Dados[]>(`${RAIZ}?arquivados=false`)).map(grupoDaApi);
}

export async function criarGrupo(corpo: { nome: string; membros: string[] }): Promise<GrupoApi> {
  return grupoDaApi(await api.post<Dados>(RAIZ, corpo));
}

export async function renomearGrupo(id: string, nome: string): Promise<GrupoApi> {
  return grupoDaApi(await api.patch<Dados>(`${RAIZ}/${id}`, { nome }));
}

/** Troca os bots do grupo (2 a 5, sem a Sora, que entra sozinha como chefe). */
export async function definirMembrosDoGrupo(id: string, membros: string[]): Promise<GrupoApi> {
  return grupoDaApi(await api.patch<Dados>(`${RAIZ}/${id}`, { membros }));
}

/** Arquiva o grupo (o histórico fica guardado). */
export const arquivarGrupo = (id: string) => api.post<void>(`/v1/canais-equipe/${id}/arquivar`);

export async function listarMensagensGrupo(id: string, depoisDe = 0): Promise<MensagemGrupoApi[]> {
  const dados = await api.get<Dados[]>(`/v1/canais-equipe/${id}/mensagens?depois_de_seq=${depoisDe}&limite=100`);
  return dados.map(mensagemDaApi).sort((a, b) => a.sequencia - b.sequencia);
}

export interface EnvioMensagemGrupo { texto: string; destinatario?: string | null; respondeA?: string | null; anexos?: string[] }

export async function enviarMensagemGrupo(id: string, corpo: EnvioMensagemGrupo): Promise<MensagemGrupoApi> {
  const dados = await api.post<Dados>(`/v1/canais-equipe/${id}/mensagens`, {
    texto: corpo.texto,
    destinatario: corpo.destinatario ?? null,
    responde_a: corpo.respondeA ?? null,
    anexos: corpo.anexos ?? [],
  });
  return mensagemDaApi(dados);
}

export async function listarTarefasGrupo(id: string): Promise<TarefaGrupoApi[]> {
  return (await api.get<Dados[]>(`/v1/canais-equipe/${id}/tarefas`)).map(tarefaDaApi);
}

export async function retomarTarefaGrupo(tarefaId: string): Promise<TarefaGrupoApi[]> {
  return (await api.post<Dados[]>(`/v1/tarefas-canal/${tarefaId}/retomar`)).map(tarefaDaApi);
}

export async function reatribuirTarefaGrupo(tarefaId: string, novoDono: string): Promise<TarefaGrupoApi[]> {
  return [tarefaDaApi(await api.post<Dados>(`/v1/tarefas-canal/${tarefaId}/reatribuir`, { novo_dono: novoDono }))];
}

export async function cancelarTarefaGrupo(tarefaId: string): Promise<TarefaGrupoApi[]> {
  return (await api.post<Dados[]>(`/v1/tarefas-canal/${tarefaId}/cancelar`)).map(tarefaDaApi);
}

export async function pararBotNoGrupo(grupoId: string, botId: string): Promise<TarefaGrupoApi[]> {
  return (await api.post<Dados[]>(`${RAIZ}/${grupoId}/membros/${botId}/parar`)).map(tarefaDaApi);
}

export async function listarPedidosAtencao(): Promise<PedidoAtencao[]> {
  return (await api.get<Dados[]>(ATENCAO)).map(pedidoDaApi);
}

export function pedidoDaApi(d: Dados): PedidoAtencao {
  const tipo = d.tipo === 'rascunho_envio' ? 'envio' : d.tipo === 'pergunta' ? 'pergunta' : 'aprovacao';
  return {
    id: texto(d.id), tipo, titulo: texto(d.titulo), resumo: texto(d.resumo) || texto(d.pergunta),
    // `acao` é o id técnico da ferramenta (ex.: propor_instrucoes): o resumo já diz o que é.
    detalhes: null, proposta: propostaDe(d.proposta) ?? null, botId: textoOuNulo(d.agente_id), grupoId: textoOuNulo(d.grupo_id), acao: textoOuNulo(d.acao),
    opcoes: lista(d.opcoes).map(item => {
      const opcao = item as Dados;
      return { rotulo: texto(opcao.rotulo), valor: texto(opcao.valor), tom: opcao.valor === 'negar' ? 'perigo' as const : 'principal' as const };
    }),
    aceitaRespostaLivre: tipo === 'pergunta' && lista(d.opcoes).length === 0,
    criadoEm: typeof d.criado_em === 'string' && Number.isFinite(Date.parse(d.criado_em)) ? Date.parse(d.criado_em) : null,
  };
}

export function propostaDaApi(d: Dados): PropostaGrupo {
  const reaproveitados = lista(d.bots_reaproveitados).map(item => {
    const bot = item as Dados;
    return { id: texto(bot.id), nome: texto(bot.nome), funcao: texto(bot.funcao), cor: texto(bot.cor), novo: false, selecionado: true };
  });
  const novos = lista(d.bots_novos).map(item => {
    const bot = item as Dados;
    return { id: texto(bot.id) || null, nome: texto(bot.nome), funcao: texto(bot.funcao), cor: texto(bot.cor), novo: true, selecionado: true };
  });
  return { id: texto(d.id), nome: texto(d.nome), motivo: textoOuNulo(d.pedido), bots: [...reaproveitados, ...novos] };
}

export function resolverPedidoAtencao(pedido: PedidoAtencao, acao: string, resposta?: string): Promise<void> {
  if (pedido.tipo === 'pergunta') return api.post<void>(`/v1/perguntas/${pedido.id}/responder`, { valor: resposta ?? acao });
  const decisao = acao === 'sempre_permitir' ? 'sempre_permitir' : acao === 'enviar' || acao === 'aprovar' ? 'permitir' : 'negar';
  return api.post<void>(`/v1/aprovacoes/${pedido.id}/decidir`, { decisao });
}

export async function aceitarPropostaGrupo(id: string): Promise<GrupoApi> {
  return grupoDaApi(await api.post<Dados>(`${RAIZ}/propostas/${id}/aceitar`));
}

/** Propostas pendentes, para o cartão sobreviver à recarga (`GET /v1/grupos/propostas`). */
export async function listarPropostasGrupo(): Promise<PropostaGrupo[]> {
  return (await api.get<Dados[]>(`${RAIZ}/propostas`)).map(propostaDaApi);
}
export const recusarPropostaGrupo = (id: string) => api.post<void>(`${RAIZ}/propostas/${id}/recusar`);
export const ajustarPropostaGrupo = (id: string, corpo: Pick<PropostaGrupo, 'nome' | 'bots'>) => api.patch<PropostaGrupo>(`${RAIZ}/propostas/${id}`, {
  nome: corpo.nome,
  bots_reaproveitados: corpo.bots.filter(bot => bot.selecionado && !bot.novo).map(bot => bot.id).filter(Boolean),
  bots_novos: corpo.bots.filter(bot => bot.selecionado && bot.novo).map(({ id, nome, funcao, cor }) => ({ id, nome, funcao, cor })),
});
