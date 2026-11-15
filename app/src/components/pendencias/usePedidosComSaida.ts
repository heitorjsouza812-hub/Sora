// Saída suave dos pedidos resolvidos. O servidor é a verdade da lista (o contador da barra lateral
// desce na hora), mas o cartão não some de uma vez: no chat vira uma linha "✓ Permitido uma vez" e
// na central a faixa sai em 200 ms.
import { useEffect, useRef, useState } from 'react';
import { ROTULOS_RESOLVIDO } from './rotulos';
import { ultimaAcao } from './registro';
import type { PedidoAtencao } from './tipos';

export const DURACAO_LINHA = 2400;
export const DURACAO_FAIXA = 200;

export interface PedidoVisivel { pedido: PedidoAtencao; saindo: boolean; rotulo: string }

/** A lista atual mais, por um instante, os pedidos que acabaram de sair (com o rótulo da decisão). */
export function usePedidosComSaida(lista: PedidoAtencao[], duracao: number): PedidoVisivel[] {
  const anterior = useRef<PedidoAtencao[]>(lista);
  const [saindo, setSaindo] = useState<PedidoVisivel[]>([]);
  useEffect(() => {
    const ids = new Set(lista.map(pedido => pedido.id));
    const sairam = anterior.current.filter(pedido => !ids.has(pedido.id) && ultimaAcao.has(pedido.id));
    anterior.current = lista;
    if (!sairam.length) return;
    const novos = sairam.map(pedido => ({ pedido, saindo: true, rotulo: ROTULOS_RESOLVIDO[ultimaAcao.get(pedido.id) ?? ''] ?? 'Resolvido' }));
    sairam.forEach(pedido => ultimaAcao.delete(pedido.id));
    setSaindo(atuais => [...atuais, ...novos]);
    setTimeout(() => setSaindo(atuais => atuais.filter(item => !novos.includes(item))), duracao);
  }, [lista, duracao]);
  return [...lista.map(pedido => ({ pedido, saindo: false, rotulo: '' })), ...saindo.filter(item => !lista.some(pedido => pedido.id === item.pedido.id))];
}
