import { useSyncExternalStore } from 'react';

export type VistaIlha = 'inicio' | 'projeto' | 'agente' | 'aprovacao';

export interface EstadoIlhaUi {
  aberta: boolean;
  vista: VistaIlha;
  agenteId: string | null;
  /** Incrementa quando uma ação externa pede para abrir ou alternar a ilha. */
  pedido: number;
}

export interface OpcoesAbrirIlha {
  /** Hover abre temporariamente; não transforma a abertura em um pedido externo/fixado. */
  porHover?: boolean;
}

let estado: EstadoIlhaUi = {
  aberta: false,
  vista: 'inicio',
  agenteId: null,
  pedido: 0,
};

const ouvintes = new Set<() => void>();
const avisar = () => ouvintes.forEach((ouvinte) => ouvinte());
const assinar = (ouvinte: () => void) => {
  ouvintes.add(ouvinte);
  return () => { ouvintes.delete(ouvinte); };
};
const ler = () => estado;

export function abrirIlha(vista: VistaIlha = 'inicio', agenteId?: string, opcoes: OpcoesAbrirIlha = {}): void {
  estado = {
    aberta: true,
    vista,
    agenteId: vista === 'agente' ? agenteId ?? null : null,
    pedido: estado.pedido + (opcoes.porHover ? 0 : 1),
  };
  avisar();
}

export function fecharIlha(): void {
  if (!estado.aberta) return;
  estado = { ...estado, aberta: false };
  avisar();
}

export function alternarIlha(): void {
  estado = { ...estado, aberta: !estado.aberta, pedido: estado.pedido + 1 };
  avisar();
}

export function useIlhaUi(): EstadoIlhaUi {
  return useSyncExternalStore(assinar, ler, ler);
}

export function useIlhaAberta(): boolean {
  return useSyncExternalStore(assinar, () => estado.aberta, () => estado.aberta);
}
