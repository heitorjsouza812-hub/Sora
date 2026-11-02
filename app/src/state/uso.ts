import { useSyncExternalStore } from 'react';
import { api, mensagemDeErro } from '../api/cliente';

export interface ItemUso {
  data: string;
  papel: string;
  provedor: string | null;
  tokens_entrada: number;
  tokens_saida: number;
  custo_usd: number;
}

interface UsoApi { itens: ItemUso[]; custo_total_usd: number }
export interface EstadoUso {
  carregando: boolean;
  itens: ItemUso[];
  custoTotalUsd: number;
  erro?: string;
}

const inicial = (): EstadoUso => ({ carregando: false, itens: [], custoTotalUsd: 0 });
let estado = inicial();
let carregamento: Promise<void> | null = null;
const ouvintes = new Set<() => void>();
const assinar = (fn: () => void) => { ouvintes.add(fn); return () => { ouvintes.delete(fn); }; };
const definir = (novo: EstadoUso) => { estado = novo; ouvintes.forEach(fn => fn()); };
export const lerUso = () => estado;
export const useUso = () => useSyncExternalStore(assinar, lerUso, lerUso);

export function carregarUso(): Promise<void> {
  if (!carregamento) {
    definir({ ...estado, carregando: true, erro: undefined });
    carregamento = api.get<UsoApi>('/v1/uso')
      .then(dados => definir({
        carregando: false,
        itens: dados.itens,
        custoTotalUsd: dados.custo_total_usd,
      }))
      .catch(erro => definir({ ...estado, carregando: false, erro: mensagemDeErro(erro) }))
      .finally(() => { carregamento = null; });
  }
  return carregamento;
}

export const totalTokens = (uso: EstadoUso) => uso.itens.reduce(
  (total, item) => total + item.tokens_entrada + item.tokens_saida,
  0,
);

export function _reiniciarUsoParaTestes() { carregamento = null; definir(inicial()); }
