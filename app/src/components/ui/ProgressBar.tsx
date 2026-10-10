/** Barra de progresso acessível: `label` vira aria-label e aria-valuetext ("Atlas: 55%, pesquisando"). */
export function ProgressBar({ value, color, label, status }: { value: number; color: string; label?: string; status?: string }) {
  const texto = `${label ? `${label}: ` : ''}${value}%${status ? `, ${status.toLowerCase()}` : ''}`;
  return (
    <div className="progress" style={{ '--agent': color } as CSSProperties}>
      <progress max={100} value={value} aria-label={label ? `Progresso de ${label}` : 'Progresso'} aria-valuetext={texto} />
    </div>
  );
}
import type { CSSProperties } from 'react';

