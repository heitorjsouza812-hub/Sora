// Indicador de carregamento da Sora (substitui spinners): orb em 'thinking' + texto com shimmer.
import { SoraOrb } from './SoraOrb';
import './mascot.css';

export interface SoraThinkingProps {
  label?: string;                  // padrão 'Sora está pensando…'
  size?: number;                   // px do orb, padrão 28
  color?: string;                  // padrão '#E2ECFF' (agentes passam a própria cor)
  layout?: 'inline' | 'stacked';   // inline (padrão): orb ao lado do texto; stacked: orb em cima (placeholders de painel)
  className?: string;
}

export function SoraThinking({
  label = 'Sora está pensando…', size = 28, color = '#E2ECFF', layout = 'inline', className,
}: SoraThinkingProps) {
  const stacked = layout === 'stacked';
  const fontSize = stacked ? Math.max(13, Math.min(16, 11 + size * 0.025)) : Math.max(13, Math.min(18, size * 0.52));
  return (
    <span
      className={`sora-thinking${stacked ? ' sora-thinking--stacked' : ''}${className ? ' ' + className : ''}`}
      role="status"
      aria-live="polite"
      style={{ fontSize }}
    >
      <SoraOrb size={size} color={color} state="thinking" glow={stacked && size >= 96} title={label} />
      {label && <span className="sora-shimmer">{label}</span>}
    </span>
  );
}

export default SoraThinking;
