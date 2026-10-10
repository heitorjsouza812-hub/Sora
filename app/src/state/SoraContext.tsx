/* oxlint-disable react/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, type Dispatch, type ReactNode } from 'react';
import type { Status } from '../types';

export type FaseSora = 'ocioso' | 'ouvindo' | 'enviado' | 'pensando' | 'planejando' | 'coordenando' | 'pronto' | 'ajustando';

export interface SoraState {
  fase: FaseSora;
  pedido: string;
  segundos: number;
  agentesVisiveis: number;
  progressos: [number, number, number];
  versao: number;
  pulseKey: number;
}

type Action =
  | { type: 'OUVIR'; ativo: boolean }
  | { type: 'ENVIAR'; pedido: string }
  | { type: 'TICK' }
  | { type: 'AJUSTAR' }
  | { type: 'REINICIAR' };

const inicial: SoraState = {
  fase: 'ocioso', pedido: '', segundos: 0, agentesVisiveis: 0,
  progressos: [0, 0, 0], versao: 1, pulseKey: 0,
};

const progresso = (segundos: number, inicio: number, fim: number) =>
  Math.max(0, Math.min(100, Math.round(((segundos - inicio) / (fim - inicio)) * 100)));

function reducer(state: SoraState, action: Action): SoraState {
  if (action.type === 'OUVIR' && (state.fase === 'ocioso' || state.fase === 'ouvindo')) {
    return { ...state, fase: action.ativo ? 'ouvindo' : 'ocioso' };
  }
  if (action.type === 'ENVIAR') {
    return { ...inicial, fase: 'enviado', pedido: action.pedido, pulseKey: state.pulseKey + 1 };
  }
  if (action.type === 'AJUSTAR') {
    return { ...state, fase: 'ajustando', segundos: 0, versao: state.versao + 1, pulseKey: state.pulseKey + 1 };
  }
  if (action.type === 'REINICIAR') return { ...inicial, pulseKey: state.pulseKey + 1 };
  if (action.type !== 'TICK') return state;

  const segundos = state.segundos + 1;
  if (state.fase === 'ajustando') {
    return segundos >= 5
      ? { ...state, fase: 'pronto', segundos, pulseKey: state.pulseKey + 1 }
      : { ...state, segundos };
  }

  const fase: FaseSora = segundos < 2 ? 'enviado'
    : segundos < 5 ? 'pensando'
      : segundos < 11 ? 'planejando'
        : segundos < 39 ? 'coordenando'
          : 'pronto';
  const agentesVisiveis = segundos < 6 ? 0 : segundos < 8 ? 1 : segundos < 10 ? 2 : 3;
  const progressos: [number, number, number] = [
    progresso(segundos, 11, 20), progresso(segundos, 20, 29), progresso(segundos, 29, 38),
  ];
  const concluidosAntes = state.progressos.filter((p) => p === 100).length;
  const concluidosAgora = progressos.filter((p) => p === 100).length;
  return {
    ...state, segundos, fase, agentesVisiveis, progressos,
    pulseKey: state.pulseKey + (agentesVisiveis > state.agentesVisiveis || concluidosAgora > concluidosAntes ? 1 : 0),
  };
}

interface SoraContextValue {
  state: SoraState;
  dispatch: Dispatch<Action>;
  enviar: (pedido: string) => void;
  statusAgente: (indice: number) => Status;
}

const SoraContext = createContext<SoraContextValue | null>(null);

export function SoraProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, inicial);
  useEffect(() => {
    if (['ocioso', 'ouvindo', 'pronto'].includes(state.fase)) return;
    const timer = window.setInterval(() => dispatch({ type: 'TICK' }), 1000);
    return () => window.clearInterval(timer);
  }, [state.fase]);

  const enviar = useCallback((pedido: string) => dispatch({ type: 'ENVIAR', pedido }), []);
  const statusAgente = useCallback((indice: number): Status => {
    if (indice >= state.agentesVisiveis) return 'aguardando';
    if (state.progressos[indice] === 100) return 'concluido';
    return state.progressos[indice] > 0 ? 'trabalhando' : 'aguardando';
  }, [state.agentesVisiveis, state.progressos]);
  const value = useMemo(() => ({ state, dispatch, enviar, statusAgente }), [state, enviar, statusAgente]);
  return <SoraContext.Provider value={value}>{children}</SoraContext.Provider>;
}

export function useSora() {
  const value = useContext(SoraContext);
  if (!value) throw new Error('useSora precisa estar dentro de SoraProvider');
  return value;
}

