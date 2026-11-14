import { useEffect, useSyncExternalStore } from 'react';
import { listarBots, obterSora, type AgenteBotSaida } from '../api/bots';

export type EstadoBot = 'livre' | 'trabalhando' | 'precisa_de_voce';

export interface BotResumo {
  id: string;
  nome: string;
  cor: string;
  funcao: string;
  estado: EstadoBot;
  ferramentas: string[];
}

let bots: BotResumo[] = [];
let carregamento: Promise<BotResumo[]> | null = null;
const ouvintes = new Set<() => void>();

const assinar = (ouvinte: () => void) => {
  ouvintes.add(ouvinte);
  return () => { ouvintes.delete(ouvinte); };
};
const notificar = () => ouvintes.forEach(ouvinte => ouvinte());
const lerBots = () => bots;

export const estadoDoBot = (agente: Pick<AgenteBotSaida, 'estado'>): EstadoBot => agente.estado;

function resumoDoBot(agente: AgenteBotSaida): BotResumo {
  return {
    id: agente.id,
    nome: agente.nome,
    cor: agente.cor,
    funcao: agente.funcao,
    estado: estadoDoBot(agente),
    ferramentas: agente.ferramentas,
  };
}

export function carregarBots(): Promise<BotResumo[]> {
  if (carregamento) return carregamento;
  carregamento = listarBots()
    .then(saida => {
      bots = saida.map(resumoDoBot);
      notificar();
      return bots;
    })
    .finally(() => { carregamento = null; });
  return carregamento;
}

/** Eventos do servidor que mudam o estado (livre/trabalhando/precisa de você) de algum bot. */
const EVENTOS_ESTADO_BOT = new Set([
  'agente.criado', 'etapa.atualizada', 'cadeia.atualizada', 'canal.tarefa', 'fila.atualizada',
  'precisa_de_voce.atualizado', 'pergunta', 'aprovacao.pedida', 'aprovacao.resolvida',
]);
let relerEm: ReturnType<typeof setTimeout> | undefined;

/** Etapa 5 (Vela): mantém o `estado` dos bots ao vivo. O estado vem derivado do servidor, então o
 *  evento só dispara uma releitura agrupada (~400 ms). Usado pela casca e pela Ilha. */
export function receberEventoBots(evento: { tipo: string }): void {
  if (!EVENTOS_ESTADO_BOT.has(evento.tipo)) return;
  clearTimeout(relerEm);
  relerEm = setTimeout(() => { void carregarBots().catch(() => undefined); }, 400);
}

/** Lista real de bots da conta. A primeira leitura hidrata pelo adaptador HTTP. */
export function useBots(): BotResumo[] {
  const lista = useSyncExternalStore(assinar, lerBots, lerBots);
  useEffect(() => { void carregarBots().catch(() => undefined); }, []);
  return lista;
}

export function _definirBotsParaTestes(lista: AgenteBotSaida[]): void {
  bots = lista.map(resumoDoBot);
  carregamento = null;
  notificar();
}

export function _reiniciarBotsParaTestes(): void {
  bots = [];
  carregamento = null;
  notificar();
}

// Id da Sora persistente da conta (GET /v1/agentes/sora), lido uma vez por sessão.
let soraId: string | undefined;
let carregandoSora: Promise<void> | null = null;
const ouvintesSora = new Set<() => void>();
const assinarSora = (ouvinte: () => void) => { ouvintesSora.add(ouvinte); return () => { ouvintesSora.delete(ouvinte); }; };
const lerSoraId = () => soraId;

export function carregarSoraId(): Promise<void> {
  if (soraId || carregandoSora) return carregandoSora ?? Promise.resolve();
  carregandoSora = obterSora()
    .then(sora => { soraId = sora.id; ouvintesSora.forEach(ouvinte => ouvinte()); })
    .finally(() => { carregandoSora = null; });
  return carregandoSora;
}

/** Pedidos de atenção da própria Sora chegam com `agente_id` = id dela. */
export function useSoraId(): string | undefined {
  const id = useSyncExternalStore(assinarSora, lerSoraId, lerSoraId);
  useEffect(() => { void carregarSoraId().catch(() => undefined); }, []);
  return id;
}

export function _definirSoraIdParaTestes(id: string | undefined): void {
  soraId = id;
  carregandoSora = null;
  ouvintesSora.forEach(ouvinte => ouvinte());
}
