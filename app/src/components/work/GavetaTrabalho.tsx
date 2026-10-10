// Gaveta do painel Trabalho: à direita no desktop (expande/recolhe por uma aba "Trabalho"),
// bottom sheet no celular. O indicador pulsa na cor do agente enquanto alguém trabalha.
import type { CSSProperties, ReactNode } from 'react';
import './work.css';

export interface GavetaTrabalhoProps {
  aberta: boolean;
  onAlternar: () => void;
  /** cor do indicador (agente trabalhando); sem cor = indicador apagado */
  corAtiva?: string | null;
  /** texto curto mostrado na aba recolhida do celular (ex.: "Atlas · perplexity.buscar") */
  resumo?: string;
  titulo?: string;
  children: ReactNode;
}

export function GavetaTrabalho({ aberta, onAlternar, corAtiva, resumo, titulo = 'Trabalho', children }: GavetaTrabalhoProps) {
  return (
    <aside className={`wk-drawer ${aberta ? 'is-open' : ''}`} style={corAtiva ? { '--agent': corAtiva } as CSSProperties : undefined} aria-label={titulo}>
      <button type="button" className="wk-tab" onClick={onAlternar} aria-expanded={aberta}>
        <i className={`wk-pulse ${corAtiva ? 'is-live' : ''}`} aria-hidden="true" />
        <span>{titulo}</span>
        {resumo && <small>{resumo}</small>}
        <b aria-hidden="true">{aberta ? '›' : '‹'}</b>
      </button>
      <div className="wk-drawer-body">{aberta && children}</div>
    </aside>
  );
}
