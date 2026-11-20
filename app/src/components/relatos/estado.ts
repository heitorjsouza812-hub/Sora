// Abre/fecha a janela "Relatar problema" de qualquer lugar (Ctrl+K, Configurações → Conta) e avisa
// a lista de relatos enviados quando um novo chega.
import { useSyncExternalStore } from 'react';

let aberta = false;
let versaoLista = 0;
const ouvintes = new Set<() => void>();
const avisar = () => { for (const cb of [...ouvintes]) cb(); };
const assinar = (cb: () => void) => { ouvintes.add(cb); return () => { ouvintes.delete(cb); }; };

export function abrirRelatarProblema(): void { aberta = true; avisar(); }
export function fecharRelatarProblema(): void { aberta = false; avisar(); }
export function useRelatarAberto(): boolean { return useSyncExternalStore(assinar, () => aberta, () => false); }

/** Muda quando um relato é enviado: a lista de Configurações → Conta recarrega. */
export function marcarRelatoEnviado(): void { versaoLista += 1; avisar(); }
export function useVersaoRelatos(): number { return useSyncExternalStore(assinar, () => versaoLista, () => 0); }
