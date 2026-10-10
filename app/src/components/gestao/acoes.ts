// Pedidos de "Renomear" e "Apagar" vindos de qualquer menu "…" (um único host mostra o Modal).
import { useSyncExternalStore } from 'react';

export type AlvoGestao = { tipo: 'agente' | 'projeto'; id: string };
export type PedidoGestao = (AlvoGestao & { acao: 'apagar' | 'renomear' }) | null;

let pedido: PedidoGestao = null;
const ouvintes = new Set<() => void>();
const avisar = () => ouvintes.forEach((f) => f());

export function pedirApagar(alvo: AlvoGestao) { pedido = { ...alvo, acao: 'apagar' }; avisar(); }
export function pedirRenomear(alvo: AlvoGestao) { pedido = { ...alvo, acao: 'renomear' }; avisar(); }
export function fecharGestao() { pedido = null; avisar(); }
export function usePedidoGestao() {
  return useSyncExternalStore((f) => { ouvintes.add(f); return () => { ouvintes.delete(f); }; }, () => pedido, () => pedido);
}
