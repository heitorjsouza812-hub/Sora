// CONTRATO do mascote. Implementação: agente "Prisma" (motor em ./orbEngine.ts).
// As telas devem usar SÓ estas props — não depender de detalhes internos.
import { useEffect, useRef } from 'react';
import type { Movimento } from '../../types';
import { OrbRenderer, mountOrb, touchOrb, unmountOrb, type OrbParams, type OrbState } from './orbEngine';

export type { OrbState };

export interface SoraOrbProps {
  size: number;                 // px (largura = altura do canvas)
  color?: string;               // padrão '#E2ECFF' (Sora); agentes passam sua cor
  state?: OrbState;             // padrão 'idle'
  movimento?: Movimento;        // padrão 'gira'
  lookAt?: { x: number; y: number } | null; // direção do olhar, -1..1
  pulseKey?: number;            // mudar o valor dispara um pulso de luz
  glow?: boolean;               // brilho no "chão" (padrão true quando size >= 96)
  className?: string;
  title?: string;               // aria-label
  seed?: number;                // dessincroniza piscar/rotação entre vários orbs (padrão 0)
  onArrived?: () => void;       // chamado quando a animação 'arriving' termina (~2,8 s)
}

export function SoraOrb({
  size, color = '#E2ECFF', state = 'idle', movimento = 'gira', lookAt = null,
  pulseKey, glow, className, title = 'Sora', seed = 0, onArrived,
}: SoraOrbProps) {
  const ref = useRef<HTMLCanvasElement>(null);
  const orb = useRef<OrbRenderer | null>(null);
  const params: OrbParams = {
    size, color, state, movimento, lookAt, pulseKey, seed, onArrived,
    glow: glow ?? size >= 96,
  };
  const latest = useRef(params);

  useEffect(() => {
    const r = new OrbRenderer(ref.current!, latest.current);
    orb.current = r;
    mountOrb(r);
    return () => { unmountOrb(r); orb.current = null; };
  }, []);

  // props mais recentes sempre chegam ao motor (inclusive o callback onArrived)
  useEffect(() => {
    latest.current = params;
    orb.current?.setParams(params);
  });

  // redesenho estático (prefers-reduced-motion) só quando algo visível muda
  const lx = lookAt?.x, ly = lookAt?.y;
  useEffect(() => {
    if (orb.current) touchOrb(orb.current);
  }, [size, color, state, movimento, lx, ly, pulseKey, params.glow, seed]);

  return (
    <canvas
      ref={ref}
      role="img"
      aria-label={title}
      className={className}
      width={Math.round(size)}
      height={Math.round(size)}
      style={{ width: size, height: size, display: 'block', flex: 'none' }}
    />
  );
}

export default SoraOrb;
