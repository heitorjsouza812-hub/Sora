import { useSyncExternalStore } from 'react';
import { listarRascunhosBot, type RascunhoBotSaida } from '../api/bots';
import { ErroApi } from '../api/cliente';
import { listarPropostasGrupo } from '../api/grupos';
import { carregarBots } from './bots';
import type { PropostaGrupo } from '../components/pendencias/tipos';

/** Rascunho mostrado no chat; depois de decidido fica no lugar com o resultado (até recarregar). */
export interface RascunhoNoChat extends RascunhoBotSaida { resolucao?: { status: 'confirmado' | 'descartado'; agenteId?: string } }
interface CartoesSora { rascunhos: RascunhoNoChat[]; propostas: PropostaGrupo[] }
let estado: CartoesSora = { rascunhos: [], propostas: [] };
const ouvintes = new Set<() => void>();
const assinar = (fn: () => void) => { ouvintes.add(fn); return () => { ouvintes.delete(fn); }; };
const definir = (proximo: CartoesSora) => { estado = proximo; ouvintes.forEach(fn => fn()); };
const texto = (valor: unknown) => typeof valor === 'string' ? valor : '';

const decididosAqui = new Set<string>();
/** O cartão chama antes de confirmar/descartar: a decisão fica visível no lugar dele. */
export function marcarRascunhoDecididoAqui(id: string): void { decididosAqui.add(id); }

// Ids já resolvidos nesta sessão: uma leitura que estava em voo quando chegou o "resolvido" não
// pode trazer o cartão de volta.
const rascunhosResolvidos = new Set<string>();
const propostasResolvidas = new Set<string>();

export function useCartoesSora(): CartoesSora { return useSyncExternalStore(assinar, () => estado, () => estado); }

/** A rota GET é a verdade. O SSE reentrega o histórico ao abrir (grupo.proposto e bot.rascunho
 *  antigos chegam antes do "resolvido" deles), então o evento só agenda uma releitura agrupada;
 *  pedido feito durante uma leitura em voo roda logo depois dela. */
const ESPERA_RELEITURA_MS = 400;
function criarReleitura(ler: () => Promise<void>) {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let emVoo: Promise<void> | null = null;
  let pendente = false;
  const executar = (): Promise<void> => {
    if (emVoo) { pendente = true; return emVoo; }
    emVoo = ler().finally(() => {
      emVoo = null;
      if (pendente) { pendente = false; void executar().catch(() => undefined); }
    });
    return emVoo;
  };
  return {
    agora: executar,
    agendar: () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => { timer = null; void executar().catch(() => undefined); }, ESPERA_RELEITURA_MS);
    },
    cancelar: () => { if (timer) clearTimeout(timer); timer = null; pendente = false; },
  };
}

const ignorarSemRota = (erro: unknown) => {
  if (erro instanceof ErroApi && (erro.status === 404 || erro.status === 405)) return;
  throw erro;
};

const releituraRascunhos = criarReleitura(async () => {
  try {
    const lista = (await listarRascunhosBot()).filter(item => !rascunhosResolvidos.has(item.id));
    const ids = new Set(lista.map(item => item.id));
    // Pendentes vêm da API; ficam também os cartões decididos aqui, com o resultado.
    definir({ ...estado, rascunhos: [...lista, ...estado.rascunhos.filter(item => item.resolucao && !ids.has(item.id))] });
  } catch (erro) { ignorarSemRota(erro); }
});

const releituraPropostas = criarReleitura(async () => {
  try {
    const lista = (await listarPropostasGrupo()).filter(item => !propostasResolvidas.has(item.id));
    definir({ ...estado, propostas: lista });
  } catch (erro) { ignorarSemRota(erro); }
});

export function receberEventoSora(evento: { tipo: string; dados: Record<string, unknown> }): void {
  const dados = evento.dados;
  if (evento.tipo === 'bot.rascunho') {
    releituraRascunhos.agendar();
  } else if (evento.tipo === 'bot.rascunho.resolvido') {
    const id = texto(dados.rascunho_id);
    if (!id) return;
    rascunhosResolvidos.add(id);
    const status = dados.status === 'confirmado' ? 'confirmado' : 'descartado';
    const agenteId = texto(dados.agente_id) || undefined;
    // Só o cartão decidido nesta tela fica no chat com o resultado. Decisões de outra aba ou
    // reentregues pelo SSE somem, para não acumular "Bot criado" antigos.
    definir({ ...estado, rascunhos: decididosAqui.has(id)
      ? estado.rascunhos.map(item => item.id === id ? { ...item, resolucao: { status, agenteId } } : item)
      : estado.rascunhos.filter(item => item.id !== id) });
    // Confirmado em outra aba ou pela UI: o bot novo precisa aparecer na barra lateral.
    if (dados.status === 'confirmado') void carregarBots().catch(() => undefined);
  } else if (evento.tipo === 'grupo.proposto') {
    releituraPropostas.agendar();
  } else if (evento.tipo === 'grupo.proposta.resolvida') {
    const id = texto(dados.proposta_id);
    if (!id) return;
    propostasResolvidas.add(id);
    definir({ ...estado, propostas: estado.propostas.filter(item => item.id !== id) });
  }
}

/** Rascunhos de bot pendentes (GET /v1/bots/rascunhos), lidos ao abrir o chat da Sora. */
export function carregarRascunhosPendentes(): Promise<void> { return releituraRascunhos.agora(); }

/** Propostas de grupo abertas (GET /v1/grupos/propostas), lidas ao abrir o chat da Sora. */
export function carregarPropostasPendentes(): Promise<void> { return releituraPropostas.agora(); }

export function _reiniciarCartoesSoraParaTestes(): void {
  releituraRascunhos.cancelar();
  releituraPropostas.cancelar();
  decididosAqui.clear();
  rascunhosResolvidos.clear();
  propostasResolvidas.clear();
  definir({ rascunhos: [], propostas: [] });
}
