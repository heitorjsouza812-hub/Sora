// Simulação de erros para demonstrar e testar os estados do item 47 (só em desenvolvimento).
// Liga por URL (?simularErro=conexao|modelo|plugin|creditos, ou ?simularErro= para desligar) ou pelo
// painel <PainelErrosDev/>. Fica na sessionStorage até ser desligada.
import { useSyncExternalStore } from 'react';

export type TipoErro = 'conexao' | 'modelo' | 'plugin' | 'creditos';
export const TIPOS_ERRO: { id: TipoErro; rotulo: string }[] = [
  { id: 'conexao', rotulo: 'Sem conexão' },
  { id: 'modelo', rotulo: 'Modelo falhou' },
  { id: 'plugin', rotulo: 'Plugin desconectado' },
  { id: 'creditos', rotulo: 'Créditos esgotados' },
];

const CHAVE = 'sora.simularErro';
const valido = (x: string | null): x is TipoErro => TIPOS_ERRO.some(t => t.id === x);
const ouvintes = new Set<() => void>();

function lerInicial(): TipoErro | null {
  if (!import.meta.env.DEV || typeof window === 'undefined') return null;
  const url = new URLSearchParams(window.location.search);
  if (url.has('simularErro')) {
    const v = url.get('simularErro');
    try { if (valido(v)) sessionStorage.setItem(CHAVE, v); else sessionStorage.removeItem(CHAVE); } catch { /* sem armazenamento */ }
    return valido(v) ? v : null;
  }
  try { const v = sessionStorage.getItem(CHAVE); return valido(v) ? v : null; } catch { return null; }
}

let atual: TipoErro | null = lerInicial();

export function definirErroSimulado(tipo: TipoErro | null) {
  if (!import.meta.env.DEV) return;
  atual = tipo;
  try { if (tipo) sessionStorage.setItem(CHAVE, tipo); else sessionStorage.removeItem(CHAVE); } catch { /* sem armazenamento */ }
  ouvintes.forEach(f => f());
}

const assinar = (f: () => void) => { ouvintes.add(f); return () => { ouvintes.delete(f); }; };
const ler = () => atual;

/** o erro simulado agora (sempre null em produção) */
export function useErroSimulado() { return useSyncExternalStore(assinar, ler, ler); }
export const lerErroSimulado = ler;

if (import.meta.env.DEV && typeof window !== 'undefined') {
  (window as unknown as { __soraErro?: unknown }).__soraErro = { definir: definirErroSimulado, ler };
}
