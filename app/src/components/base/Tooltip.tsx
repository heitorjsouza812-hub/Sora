// Tooltip: abre no hover (com atraso) e no foco do teclado; Esc fecha sem fechar o diálogo de fora.
// O balão continua aberto com o mouse em cima dele (WCAG 1.4.13). Não recebe foco; liga por aria-describedby.
import {
  cloneElement, useEffect, useId, useLayoutEffect, useRef, useState,
  type ReactElement, type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import './base.css';

type PropsFilho = { 'aria-describedby'?: string };

export interface TooltipProps {
  conteudo: ReactNode;
  /** um único elemento focável (botão, link…) */
  children: ReactElement<PropsFilho>;
  lado?: 'cima' | 'baixo';
  /** atraso do hover em ms (o foco abre na hora) */
  atraso?: number;
}

export function Tooltip({ conteudo, children, lado = 'cima', atraso = 350 }: TooltipProps) {
  const [aberto, setAberto] = useState(false);
  const [pos, setPos] = useState({ top: -9999, left: -9999, lado });
  const [ancora, setAncora] = useState<HTMLElement | null>(null);
  const balao = useRef<HTMLDivElement>(null);
  const timer = useRef(0);
  const id = useId();
  const p = children.props;

  const abrir = (ms: number) => { window.clearTimeout(timer.current); timer.current = window.setTimeout(() => setAberto(true), ms); };
  const fechar = (ms = 0) => { window.clearTimeout(timer.current); timer.current = window.setTimeout(() => setAberto(false), ms); };
  useEffect(() => () => window.clearTimeout(timer.current), []);

  useLayoutEffect(() => {
    if (!aberto) return;
    const a = ancora?.getBoundingClientRect();
    const b = balao.current?.getBoundingClientRect();
    if (!a || !b) return;
    const gap = 8;
    let l = lado;
    if (l === 'cima' && a.top - b.height - gap < 8) l = 'baixo';
    else if (l === 'baixo' && a.bottom + b.height + gap > window.innerHeight - 8) l = 'cima';
    const top = l === 'cima' ? a.top - b.height - gap : a.bottom + gap;
    const left = Math.max(8, Math.min(window.innerWidth - b.width - 8, a.left + a.width / 2 - b.width / 2));
    setPos({ top, left, lado: l });
  }, [aberto, ancora, lado, conteudo]);

  // só o aria-describedby vai para o filho; os eventos sobem até o invólucro (inline-flex, sem caixa própria)
  const gatilho = cloneElement(children, {
    'aria-describedby': [p['aria-describedby'], aberto ? id : undefined].filter(Boolean).join(' ') || undefined,
  });

  return <>
    <span className="b-tooltip-alvo"
      onMouseEnter={(e) => { setAncora(e.currentTarget.firstElementChild as HTMLElement | null); abrir(atraso); }}
      onMouseLeave={() => fechar(120)}
      onFocus={(e) => { setAncora(e.target); if (e.target.matches(':focus-visible')) abrir(0); }}
      onBlur={() => fechar()}
      onKeyDown={(e) => { if (e.key === 'Escape' && aberto) { e.stopPropagation(); fechar(); } }}>
      {gatilho}
    </span>
    {aberto && typeof document !== 'undefined' && createPortal(
      <div ref={balao} id={id} role="tooltip" className="b-tooltip" data-lado={pos.lado} style={{ top: pos.top, left: pos.left }}
        onMouseEnter={() => window.clearTimeout(timer.current)} onMouseLeave={() => fechar(120)}>
        {conteudo}
      </div>,
      document.body,
    )}
  </>;
}
