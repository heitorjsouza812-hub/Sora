import { useEffect, useSyncExternalStore } from 'react';
import { listarPedidosAtencao, resolverPedidoAtencao } from '../api/grupos';
import type { PedidoAtencao } from '../components/pendencias/tipos';

interface EstadoAtencao {
  lista: PedidoAtencao[];
  carregando: boolean;
  carregado: boolean;
  erro: string | null;
  porBot: Record<string, number>;
  porGrupo: Record<string, number>;
}

function contar(lista: PedidoAtencao[]) {
  const porBot: Record<string, number> = {};
  const porGrupo: Record<string, number> = {};
  for (const pedido of lista) {
    if (pedido.botId) porBot[pedido.botId] = (porBot[pedido.botId] ?? 0) + 1;
    if (pedido.grupoId) porGrupo[pedido.grupoId] = (porGrupo[pedido.grupoId] ?? 0) + 1;
  }
  return { porBot, porGrupo };
}

const inicial = (): EstadoAtencao => ({ lista: [], carregando: false, carregado: false, erro: null, porBot: {}, porGrupo: {} });
let estado = inicial();
const ouvintes = new Set<() => void>();
const definirLista = (lista: PedidoAtencao[], demais: Partial<EstadoAtencao> = {}) => {
  estado = { ...estado, ...demais, lista, ...contar(lista) };
  ouvintes.forEach(fn => fn());
};
const mensagem = (erro: unknown) => erro instanceof Error ? erro.message : 'Não foi possível concluir esta decisão.';

export const lerPrecisaDeVoce = () => estado;
export function usePrecisaDeVoce() {
  const atual = useSyncExternalStore(fn => { ouvintes.add(fn); return () => { ouvintes.delete(fn); }; }, lerPrecisaDeVoce, lerPrecisaDeVoce);
  useEffect(() => { void carregarPrecisaDeVoce().catch(() => undefined); }, []);
  return atual;
}

// Releitura pedida durante uma leitura em andamento: a resposta em voo pode já estar velha.
let releituraPendente = false;

export async function carregarPrecisaDeVoce(forcar = false): Promise<void> {
  if (estado.carregando) { if (forcar) releituraPendente = true; return; }
  if (estado.carregado && !forcar) return;
  definirLista(estado.lista, { carregando: true, erro: null });
  try {
    definirLista(await listarPedidosAtencao(), { carregando: false, carregado: true, erro: null });
  } catch (erro) {
    definirLista(estado.lista, { carregando: false, carregado: true, erro: mensagem(erro) });
    throw erro;
  } finally {
    if (releituraPendente) { releituraPendente = false; void carregarPrecisaDeVoce(true).catch(() => undefined); }
  }
}

const EVENTOS_ATENCAO = new Set(['precisa_de_voce.atualizado', 'pergunta', 'aprovacao.pedida', 'aprovacao.resolvida']);
let relerAtencaoEm: ReturnType<typeof setTimeout> | undefined;

/** Etapa 5 (Vela): o servidor é a verdade dos pedidos. Depois de qualquer evento de atenção relê a
 *  lista (agrupado, ~400 ms), porque o evento por escopo pode não trazer o pedido (ex.: pergunta de
 *  um especialista da cadeia, cujo pedido pertence à conversa da Sora). Serve ao app e à Ilha. */
export function receberEventoAtencao(evento: { tipo: string }): void {
  if (!EVENTOS_ATENCAO.has(evento.tipo)) return;
  clearTimeout(relerAtencaoEm);
  relerAtencaoEm = setTimeout(() => { void carregarPrecisaDeVoce(true).catch(() => undefined); }, 400);
}

export function receberPedidoAtencao(pedido: PedidoAtencao): void {
  definirLista([...estado.lista.filter(item => item.id !== pedido.id), pedido]);
}

export function removerPedidoAtencao(id: string): void {
  definirLista(estado.lista.filter(item => item.id !== id));
}

export async function decidirPedidoAtencao(id: string, acao: string, resposta?: string): Promise<void> {
  const pedido = estado.lista.find(item => item.id === id);
  if (!pedido) return;
  definirLista(estado.lista.map(item => item.id === id ? { ...item, enviando: true, erro: null } : item));
  try {
    await resolverPedidoAtencao(pedido, acao, resposta);
    removerPedidoAtencao(id);
  } catch (erro) {
    definirLista(estado.lista.map(item => item.id === id ? { ...item, enviando: false, erro: mensagem(erro) } : item));
    throw erro;
  }
}

export function _reiniciarAtencaoParaTestes(): void { releituraPendente = false; definirLista([], { carregando: false, carregado: false, erro: null }); }
