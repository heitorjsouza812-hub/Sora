// Badge: rótulo curto de status. Tom "agente" usa a cor do agente (--agent-color).
import type { CSSProperties, HTMLAttributes, ReactNode } from 'react';
import './base.css';

export type TomBadge = 'neutro' | 'sucesso' | 'aviso' | 'erro' | 'agente';

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tom?: TomBadge;
  /** cor do agente (só com tom="agente") */
  cor?: string;
  /** bolinha antes do texto; "pulso" = trabalhando */
  ponto?: boolean | 'pulso';
  children: ReactNode;
}

export function Badge({ tom = 'neutro', cor, ponto, className, style, children, ...resto }: BadgeProps) {
  const estilo = cor ? { ...style, '--agent-color': cor } as CSSProperties : style;
  return (
    <span className={['b-badge', `b-badge--${tom}`, className ?? ''].filter(Boolean).join(' ')} style={estilo} {...resto}>
      {ponto && <i className={ponto === 'pulso' ? 'b-badge__ponto is-pulso' : 'b-badge__ponto'} aria-hidden="true" />}
      {children}
    </span>
  );
}
