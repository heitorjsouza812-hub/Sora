// Créditos de uso (item 49) — 100% simulado no navegador.
// • Saldo do plano: 2.000 créditos/mês; a conta de exemplo começa com 760 usados (1.240 restantes).
// • Cada passo concluído de um agente cobra créditos (ferramentas e entregas custam mais).
// • A cobrança é incremental por execução: apagar um projeto NÃO devolve créditos.
// Persistido em localStorage (com try/catch), como o store de projetos.
import { useSyncExternalStore } from 'react';
import { passosDaExecucao, type EstadoProjetos } from './projetos';

export const LIMITE_PADRAO = 2000;
export const USADOS_INICIAIS = 760;
export const LIMIAR_AVISO = 0.1;               // < 10% restantes → aviso
export const CUSTO_PASSO: Record<string, number> = { ferramenta: 6, entrega: 8, pensamento: 2, prompt: 1, handoff: 1 };

export interface EstadoCreditos {
  versao: 1;
  limite: number;
  usados: number;
  cobrados: Record<string, number>;           // execucaoId → créditos já cobrados
  avisado: boolean;                            // aviso de < 10% já mostrado neste ciclo
}

const CHAVE = 'sora.creditos.v1';
const inicial = (): EstadoCreditos => ({ versao: 1, limite: LIMITE_PADRAO, usados: USADOS_INICIAIS, cobrados: {}, avisado: false });

function carregar(): EstadoCreditos {
  try {
    const bruto = localStorage.getItem(CHAVE);
    if (!bruto) return inicial();
    const e = JSON.parse(bruto) as EstadoCreditos;
    return e?.versao === 1 && typeof e.usados === 'number' ? { ...inicial(), ...e } : inicial();
  } catch { return inicial(); }
}

let estado: EstadoCreditos = typeof window === 'undefined' ? inicial() : carregar();
const ouvintes = new Set<() => void>();

function definir(proximo: EstadoCreditos) {
  estado = proximo;
  ouvintes.forEach((f) => f());
  try { localStorage.setItem(CHAVE, JSON.stringify(estado)); } catch { /* sem armazenamento: só em memória */ }
}

const assinar = (f: () => void) => { ouvintes.add(f); return () => { ouvintes.delete(f); }; };
const ler = () => estado;
export const lerCreditos = ler;

/** Saldo e estado derivados. */
export function resumoCreditos(e: EstadoCreditos = estado) {
  const restantes = Math.max(0, e.limite - e.usados);
  const fracao = e.limite ? restantes / e.limite : 0;
  return { restantes, limite: e.limite, usados: Math.min(e.usados, e.limite), fracao, acabando: fracao < LIMIAR_AVISO, esgotado: restantes <= 0 };
}

export function useCreditos() { return useSyncExternalStore(assinar, ler, ler); }

/** Cobra os passos concluídos desde a última sincronização. */
export function sincronizarCreditos(projetos: EstadoProjetos, agora: number) {
  let novos = 0;
  let cobrados: Record<string, number> | null = null;
  for (const x of projetos.execucoes) {
    const custo = passosDaExecucao(x, agora)
      .filter((p) => p.status === 'concluido')
      .reduce((s, p) => s + (CUSTO_PASSO[p.tipo] ?? 1), 0);
    const ja = estado.cobrados[x.id] ?? 0;
    if (custo > ja) {
      cobrados ??= { ...estado.cobrados };
      cobrados[x.id] = custo;
      novos += custo - ja;
    }
  }
  if (!cobrados) return;
  definir({ ...estado, usados: Math.min(estado.limite, estado.usados + novos), cobrados });
}

/** O aviso de saldo baixo já foi mostrado neste ciclo. */
export function marcarAvisoCreditos() { if (!estado.avisado) definir({ ...estado, avisado: true }); }

/** Simulação: renova o ciclo (volta ao saldo cheio). */
export function renovarCreditos() { definir({ ...estado, usados: 0, avisado: false }); }

/** QA: volta ao estado de exemplo. */
export function reiniciarCreditos() { definir(inicial()); }

if (import.meta.env.DEV && typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).__creditos = {
    ler, reiniciar: reiniciarCreditos, renovar: renovarCreditos,
    gastar: (n: number) => definir({ ...estado, usados: Math.min(estado.limite, estado.usados + n) }),
  };
}
