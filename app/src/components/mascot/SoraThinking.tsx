// Indicador de carregamento da Sora (substitui spinners): orb pequeno em 'thinking' + texto com shimmer.
import { SoraOrb } from './SoraOrb';
import './mascot.css';

export interface SoraThinkingProps {
  label?: string;   // padrão 'Sora está pensando…'
  size?: number;    // px do orb, padrão 28
  color?: string;   // padrão '#E2ECFF' (agentes passam a própria cor)
  className?: string;
}

export function SoraThinking({ label = 'Sora está pensando…', size = 28, color = '#E2ECFF', className }: SoraThinkingProps) {
  return (
    <span
      className={'sora-thinking' + (className ? ' ' + className : '')}
      role="status"
      aria-live="polite"
      style={{ fontSize: Math.max(13, Math.min(18, size * 0.52)) }}
    >
      <SoraOrb size={size} color={color} state="thinking" glow={false} title={label} />
      {label && <span className="sora-shimmer">{label}</span>}
    </span>
  );
}

export default SoraThinking;
