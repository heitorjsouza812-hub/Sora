// Fila global de toasts (separada do componente para o Fast Refresh). Veja Toast.tsx.
import { useSyncExternalStore, type ReactNode } from 'react';

export type TomToast = 'neutro' | 'sucesso' | 'aviso' | 'erro';

export interface ToastOpcoes {
  mensagem: ReactNode;
  descricao?: ReactNode;
  tom?: TomToast;
  acao?: { rotulo: string; onClick: () => void };
  /** ms até fechar sozinho; 0 = só fecha manualmente. Padrão 5000 (7000 com ação) */
  duracao?: number;
}

export interface ToastItem extends ToastOpcoes { id: number }

let fila: ToastItem[] = [];
let seq = 0;
const ouvintes = new Set<() => void>();
export const avisarToasts = () => ouvintes.forEach((f) => f());

/** Mostra um toast e devolve o id (para fechar antes do tempo). */
export function toast(op: ToastOpcoes): number {
  const id = ++seq;
  fila = [...fila, { ...op, id }];
  avisarToasts();
  return id;
}
export function fecharToast(id: number) { fila = fila.filter((t) => t.id !== id); avisarToasts(); }

export const assinarToasts = (f: () => void) => { ouvintes.add(f); return () => { ouvintes.delete(f); }; };
export const lerToasts = () => fila;

export function useToast() { return { mostrar: toast, fechar: fecharToast }; }

// Se mais de um ToastProvider for montado (raiz do app + catálogo), só o primeiro desenha a região.
let donos: number[] = [];
let donoSeq = 0;
export const novoDono = () => ++donoSeq;
export function registrarDono(id: number) {
  donos = [...donos, id]; avisarToasts();
  return () => { donos = donos.filter((d) => d !== id); avisarToasts(); };
}
const lerDono = () => donos[0] ?? 0;
export const useDonoToasts = () => useSyncExternalStore(assinarToasts, lerDono, lerDono);
export const useFilaToasts = () => useSyncExternalStore(assinarToasts, lerToasts, lerToasts);
