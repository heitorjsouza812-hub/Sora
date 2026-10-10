// Abre/fecha o "Editar agente" de qualquer lugar do app (um único host montado no AppShell).
import { useSyncExternalStore } from 'react';

let aberto: string | null = null;
const ouvintes = new Set<() => void>();
const avisar = () => ouvintes.forEach((f) => f());

/** Abre o editor para um agente (ou 'sora'). */
export function abrirEditorAgente(agenteId: string) { aberto = agenteId; avisar(); }
export function fecharEditorAgente() { aberto = null; avisar(); }
export function useEditorAberto() {
  return useSyncExternalStore((f) => { ouvintes.add(f); return () => { ouvintes.delete(f); }; }, () => aberto, () => aberto);
}
