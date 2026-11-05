// Peças de equipe da etapa 4: canais, tarefas, fila de cada agente, medidor de contexto e abas do navegador.
// Os eventos chegam pelo GET /v1/eventos (mesmo stream do resto do app) com os campos exatos de
// backend/app/eventos/equipe.py; o estado inicial vem das rotas REST (sem simulação).
import { useSyncExternalStore } from 'react';
import { api } from '../api/cliente';
import type { EventoSse } from '../api/eventos';

export type NivelContexto = 'ok' | 'atencao' | 'compactar' | 'cheio';
export interface Contexto { agenteId: string; fio: string; porcentagem: number; tokens: number; janela: number; estimado: boolean; nivel: NivelContexto; compactacao: 'parada' | 'compactando' | 'falhou' }
export interface ItemFila { itemId: string; seq: number; pista: string; origem: string; previa: string; status: string; esperandoPor: string | null; emEdicao: boolean }
export interface Fila { agenteId: string; pausada: boolean; limiteTarefas: number; itens: ItemFila[] }
export interface Canal { id: string; nome: string; membros: string[]; liderId: string | null; arquivado: boolean }
export interface MensagemCanal { id: string; canalId: string; seq: number; autor: 'usuario' | 'agente' | 'sistema'; agenteId: string | null; tipo: 'mensagem' | 'atividade' | 'resultado'; texto: string; respondeA: string | null; tarefaId: string | null; anexos: string[]; criadaEm: string }
export type AcaoTarefa = 'parar' | 'retomar' | 'reatribuir' | 'cancelar';
export interface TarefaCanal { id: string; canalId: string; donoId: string; paiId: string | null; status: string; motivo: string | null; revisao: number; acoes: AcaoTarefa[] }
export interface AbaNavegador { id: string; agenteId: string; url: string; titulo: string; carregada: boolean; assumida: boolean; pedidoDeAjuda: string | null }

export interface EstadoEquipe {
  canais: Record<string, Canal>;
  mensagens: Record<string, MensagemCanal[]>;
  tarefas: Record<string, TarefaCanal>;
  filas: Record<string, Fila>;
  contextos: Record<string, Contexto>;
  reacoes: Record<string, Record<string, number>>;
  abas: Record<string, AbaNavegador>;
}
export const equipeInicial = (): EstadoEquipe => ({ canais: {}, mensagens: {}, tarefas: {}, filas: {}, contextos: {}, reacoes: {}, abas: {} });

type Dados = Record<string, unknown>;
const txt = (v: unknown) => typeof v === 'string' ? v : '';
const txtOuNulo = (v: unknown) => typeof v === 'string' && v ? v : null;
const num = (v: unknown, p = 0) => typeof v === 'number' ? v : p;
const lista = (v: unknown): unknown[] => Array.isArray(v) ? v : [];
export const chaveContexto = (agenteId: string, fio: string) => `${agenteId}:${fio}`;

export const canalDe = (d: Dados): Canal => ({ id: txt(d.canal_id), nome: txt(d.nome), membros: lista(d.membros).map(String), liderId: txtOuNulo(d.lider_id), arquivado: d.arquivado === true });
export const mensagemDe = (d: Dados): MensagemCanal => ({
  id: txt(d.mensagem_id), canalId: txt(d.canal_id), seq: num(d.seq),
  autor: d.autor === 'agente' ? 'agente' : d.autor === 'sistema' ? 'sistema' : 'usuario', agenteId: txtOuNulo(d.agente_id),
  tipo: d.tipo === 'atividade' ? 'atividade' : d.tipo === 'resultado' ? 'resultado' : 'mensagem', texto: txt(d.texto),
  respondeA: txtOuNulo(d.responde_a), tarefaId: txtOuNulo(d.tarefa_id), anexos: lista(d.anexos).map(String), criadaEm: txt(d.criada_em),
});
export const tarefaDe = (d: Dados): TarefaCanal => ({
  id: txt(d.tarefa_id), canalId: txt(d.canal_id), donoId: txt(d.dono_id), paiId: txtOuNulo(d.pai_id), status: txt(d.status),
  motivo: txtOuNulo(d.motivo), revisao: num(d.revisao), acoes: lista(d.acoes).filter((a): a is AcaoTarefa => ['parar', 'retomar', 'reatribuir', 'cancelar'].includes(String(a))),
});
export const filaDe = (d: Dados): Fila => ({
  agenteId: txt(d.agente_id), pausada: d.pausada === true, limiteTarefas: num(d.limite_tarefas, 1),
  itens: (lista(d.itens) as Dados[]).map(i => ({ itemId: txt(i.item_id), seq: num(i.seq), pista: txt(i.pista), origem: txt(i.origem), previa: txt(i.previa), status: txt(i.status), esperandoPor: txtOuNulo(i.esperando_por), emEdicao: i.em_edicao === true })),
});
export const contextoDe = (d: Dados): Contexto => ({
  agenteId: txt(d.agente_id), fio: txt(d.fio) || 'principal', porcentagem: num(d.porcentagem), tokens: num(d.tokens), janela: num(d.janela), estimado: d.estimado === true,
  nivel: (['ok', 'atencao', 'compactar', 'cheio'].includes(txt(d.nivel)) ? txt(d.nivel) : 'ok') as NivelContexto,
  compactacao: d.compactacao === 'compactando' ? 'compactando' : d.compactacao === 'falhou' ? 'falhou' : 'parada',
});
export const abaDe = (d: Dados): AbaNavegador => ({ id: txt(d.aba_id), agenteId: txt(d.agente_id), url: txt(d.url), titulo: txt(d.titulo), carregada: d.carregada === true, assumida: d.assumida_pelo_usuario === true, pedidoDeAjuda: txtOuNulo(d.pedido_de_ajuda) });

/** Insere ou troca a mensagem pelo id (idempotente: o SSE repete eventos ao reconectar) e mantém a ordem por seq. */
function inserirMensagem(lista: MensagemCanal[], m: MensagemCanal): MensagemCanal[] {
  const sem = lista.filter(x => x.id !== m.id);
  return [...sem, m].sort((a, b) => a.seq - b.seq);
}
/** Evento de tarefa antigo (revisão menor) não desfaz um estado mais novo. */
function tarefaMaisNova(atual: TarefaCanal | undefined, nova: TarefaCanal): TarefaCanal { return atual && atual.revisao > nova.revisao ? atual : nova; }

/** Redutor puro dos eventos de equipe. Eventos desconhecidos devolvem o mesmo objeto. */
export function aplicarEventoEquipe(e: EstadoEquipe, ev: Pick<EventoSse, 'tipo' | 'dados'>): EstadoEquipe {
  const d = ev.dados as Dados;
  switch (ev.tipo) {
    case 'canal.atualizado': { const c = canalDe(d); return c.id ? { ...e, canais: { ...e.canais, [c.id]: c } } : e; }
    case 'canal.mensagem': { const m = mensagemDe(d); return m.id && m.canalId ? { ...e, mensagens: { ...e.mensagens, [m.canalId]: inserirMensagem(e.mensagens[m.canalId] ?? [], m) } } : e; }
    case 'canal.tarefa': { const t = tarefaDe(d); return t.id ? { ...e, tarefas: { ...e.tarefas, [t.id]: tarefaMaisNova(e.tarefas[t.id], t) } } : e; }
    case 'fila.atualizada': { const f = filaDe(d); return f.agenteId ? { ...e, filas: { ...e.filas, [f.agenteId]: f } } : e; }
    case 'contexto.atualizado': { const c = contextoDe(d); return c.agenteId ? { ...e, contextos: { ...e.contextos, [chaveContexto(c.agenteId, c.fio)]: c } } : e; }
    case 'reacao': {
      const id = txt(d.mensagem_id), emoji = txt(d.emoji); if (!id || !emoji) return e;
      const atual = e.reacoes[id] ?? {}; const n = Math.max(0, (atual[emoji] ?? 0) + (d.ligada === true ? 1 : -1));
      const { [emoji]: _, ...resto } = atual;
      return { ...e, reacoes: { ...e.reacoes, [id]: n > 0 ? { ...resto, [emoji]: n } : resto } };
    }
    case 'navegador.aba': {
      const a = abaDe(d); if (!a.id) return e;
      if (d.fechada === true) { const { [a.id]: _, ...resto } = e.abas; return { ...e, abas: resto }; }
      return { ...e, abas: { ...e.abas, [a.id]: a } };
    }
    default: return e;
  }
}

// ── Store ────────────────────────────────────────────────────────────────────────────────

let estado = equipeInicial();
const ouvintes = new Set<() => void>();
const definir = (p: EstadoEquipe) => { estado = p; ouvintes.forEach(f => f()); };
export const lerEquipe = () => estado;
export function useEquipe() { return useSyncExternalStore(fn => { ouvintes.add(fn); return () => { ouvintes.delete(fn); }; }, lerEquipe, lerEquipe); }
export function receberEventoEquipe(ev: Pick<EventoSse, 'tipo' | 'dados'>) { const p = aplicarEventoEquipe(estado, ev); if (p !== estado) definir(p); }
export function reiniciarEquipe() { definir(equipeInicial()); }

// ── API (corpo e resposta como em .maestri/contrato-etapa4.md) ──────────────────────────

const aplicarVarios = (tipo: string, itens: Dados[]) => itens.forEach(dados => receberEventoEquipe({ tipo, dados }));

export async function carregarCanais(arquivados = false): Promise<void> {
  aplicarVarios('canal.atualizado', await api.get<Dados[]>(`/v1/canais-equipe?arquivados=${arquivados}`));
}
export async function carregarMensagensCanal(canalId: string, depoisDeSeq = 0): Promise<void> {
  aplicarVarios('canal.mensagem', await api.get<Dados[]>(`/v1/canais-equipe/${canalId}/mensagens?depois_de_seq=${depoisDeSeq}&limite=50`));
}
export async function carregarTarefasCanal(canalId: string): Promise<void> {
  aplicarVarios('canal.tarefa', await api.get<Dados[]>(`/v1/canais-equipe/${canalId}/tarefas`));
}
export async function enviarAoCanal(canalId: string, texto: string, destinatario?: string): Promise<void> {
  const m = await api.post<Dados>(`/v1/canais-equipe/${canalId}/mensagens`, { texto, destinatario: destinatario ?? null, anexos: [] });
  receberEventoEquipe({ tipo: 'canal.mensagem', dados: m });
}
export async function criarCanal(corpo: { nome: string; membros: string[]; lider_id?: string | null; proposito?: string; instrucoes?: string }): Promise<void> {
  receberEventoEquipe({ tipo: 'canal.atualizado', dados: await api.post<Dados>('/v1/canais-equipe', corpo) });
}
export const arquivarCanal = (id: string) => api.post<void>(`/v1/canais-equipe/${id}/arquivar`);
export const restaurarCanal = (id: string) => api.post<void>(`/v1/canais-equipe/${id}/restaurar`);
export async function agirNaTarefa(id: string, acao: Exclude<AcaoTarefa, 'reatribuir'>): Promise<void> {
  aplicarVarios('canal.tarefa', await api.post<Dados[]>(`/v1/tarefas-canal/${id}/${acao}`));
}
export async function reatribuirTarefa(id: string, novoDono: string): Promise<void> {
  receberEventoEquipe({ tipo: 'canal.tarefa', dados: await api.post<Dados>(`/v1/tarefas-canal/${id}/reatribuir`, { novo_dono: novoDono }) });
}
export async function reagirA(mensagemId: string, emoji: string): Promise<void> {
  const resumo = await api.post<Record<string, number>>(`/v1/mensagens/${mensagemId}/reacoes`, { emoji });
  definir({ ...estado, reacoes: { ...estado.reacoes, [mensagemId]: resumo } });
}

export async function carregarFila(agenteId: string): Promise<void> { receberEventoEquipe({ tipo: 'fila.atualizada', dados: await api.get<Dados>(`/v1/agentes/${agenteId}/fila`) }); }
export async function agirNaFila(agenteId: string, caminho: string, corpo?: unknown): Promise<void> {
  receberEventoEquipe({ tipo: 'fila.atualizada', dados: await api.post<Dados>(`/v1/agentes/${agenteId}/fila/${caminho}`, corpo) });
}
export const pausarFila = (id: string) => agirNaFila(id, 'pausar');
export const retomarFila = (id: string) => agirNaFila(id, 'retomar');
export const cancelarItemFila = (id: string, item: string) => agirNaFila(id, `${item}/cancelar`);
export const repetirItemFila = (id: string, item: string) => agirNaFila(id, `${item}/repetir`);

export async function carregarContexto(agenteId: string): Promise<void> { aplicarVarios('contexto.atualizado', await api.get<Dados[]>(`/v1/agentes/${agenteId}/contexto`)); }
export async function compactarAgora(agenteId: string, fio = 'principal'): Promise<void> {
  receberEventoEquipe({ tipo: 'contexto.atualizado', dados: await api.post<Dados>(`/v1/agentes/${agenteId}/contexto/compactar?fio=${encodeURIComponent(fio)}`) });
}

export async function carregarAbas(agenteId?: string): Promise<void> {
  aplicarVarios('navegador.aba', await api.get<Dados[]>(`/v1/navegador/abas${agenteId ? `?agente_id=${agenteId}` : ''}`));
}
export async function assumirAba(id: string): Promise<void> { receberEventoEquipe({ tipo: 'navegador.aba', dados: await api.post<Dados>(`/v1/navegador/abas/${id}/assumir`) }); }
export async function devolverAba(id: string): Promise<void> { receberEventoEquipe({ tipo: 'navegador.aba', dados: await api.post<Dados>(`/v1/navegador/abas/${id}/devolver`) }); }
export async function fecharAba(id: string): Promise<void> { await api.delete<void>(`/v1/navegador/abas/${id}`); receberEventoEquipe({ tipo: 'navegador.aba', dados: { aba_id: id, fechada: true } }); }
