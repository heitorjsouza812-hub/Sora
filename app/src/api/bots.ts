import type { PreferenciasConversa } from './preferenciasConversa';
import { api } from './cliente';
import type { Movimento } from '../types';

export type EstadoBotApi = 'livre' | 'trabalhando' | 'precisa_de_voce';

export interface AgenteBotSaida extends Partial<PreferenciasConversa> {
  criado_em?: string;
  id: string;
  tipo: 'sora' | 'individual' | 'especialista';
  nome: string;
  funcao: string;
  cor: string;
  movimento: Movimento;
  ferramentas: string[];
  estado: EstadoBotApi;
}

export interface RotinaRascunhoBot {
  descricao: string;
  agendamento: string;
  fuso: string;
}

export interface RascunhoBotSaida {
  id: string;
  nome: string;
  funcao: string;
  cor: string;
  instrucoes: string;
  ferramentas: string[];
  rotina: RotinaRascunhoBot | null;
  status: 'rascunho';
}

export type AjustesRascunhoBot = Partial<Pick<RascunhoBotSaida,
  'nome' | 'funcao' | 'cor' | 'instrucoes' | 'ferramentas' | 'rotina'>>;

const normalizarAgente = (agente: AgenteBotSaida): AgenteBotSaida => ({
  ...agente,
  ferramentas: Array.isArray(agente.ferramentas) ? agente.ferramentas : [],
  estado: agente.estado === 'trabalhando' || agente.estado === 'precisa_de_voce' ? agente.estado : 'livre',
});

export async function obterSora(): Promise<AgenteBotSaida> {
  return normalizarAgente(await api.get<AgenteBotSaida>('/v1/agentes/sora'));
}

export async function listarBots(): Promise<AgenteBotSaida[]> {
  const agentes = await api.get<AgenteBotSaida[]>('/v1/agentes');
  // Bot é só o agente individual persistente: a Sora e os especialistas internos que uma conversa
  // cria por baixo não aparecem na casca (barra lateral, Ctrl+K, Bots, escolha de membros).
  return agentes.filter(agente => agente.tipo === 'individual').map(normalizarAgente);
}

export async function listarRascunhosBot(): Promise<RascunhoBotSaida[]> {
  const lista = await api.get<RascunhoBotSaida[]>('/v1/bots/rascunhos');
  return Array.isArray(lista) ? lista.filter(item => item.status === 'rascunho') : [];
}

export function criarRascunhoBot(descricao: string): Promise<RascunhoBotSaida> {
  return api.post<RascunhoBotSaida>('/v1/bots/rascunhos', { descricao });
}

export function confirmarRascunhoBot(id: string, ajustes: AjustesRascunhoBot): Promise<AgenteBotSaida> {
  return api.post<AgenteBotSaida>(`/v1/bots/rascunhos/${id}/confirmar`, ajustes);
}

export function descartarRascunhoBot(id: string): Promise<void> {
  return api.delete<void>(`/v1/bots/rascunhos/${id}`);
}

export const criarBotPorDescricao = (descricao: string, preferencias?: PreferenciasConversa) => api.post<AgenteBotSaida>('/v1/bots/criar-por-descricao', { descricao, ...preferencias, ...(preferencias?.permissao === 'total' ? { confirmar_total: true } : {}) });
