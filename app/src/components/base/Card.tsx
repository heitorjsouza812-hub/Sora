// Card: superfície 1 (painel), 2 (painel elevado) ou 3 (destaque), com espaçamento P/M/G.
import type { HTMLAttributes, ReactNode } from 'react';
import './base.css';

export interface CardProps extends HTMLAttributes<HTMLElement> {
  superficie?: 1 | 2 | 3;
  espaco?: 'P' | 'M' | 'G';
  como?: 'div' | 'section' | 'article' | 'li';
  /** realça a borda no hover/foco interno (cards clicáveis) */
  interativo?: boolean;
  children: ReactNode;
}

export function Card({ superficie = 1, espaco = 'M', como: Tag = 'div', interativo, className, children, ...resto }: CardProps) {
  return (
    <Tag className={['b-card', `b-card--s${superficie}`, `b-card--${espaco}`, interativo ? 'is-interativo' : '', className ?? ''].filter(Boolean).join(' ')} {...resto}>
      {children}
    </Tag>
  );
}
