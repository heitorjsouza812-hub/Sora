import { calendario } from '../../data/mock';

export function Calendar({ compact = false, progress = 100 }: { compact?: boolean; progress?: number }) {
  const visible = Math.ceil((Math.max(0, Math.min(100, progress)) / 100) * calendario.length);
  const tipos = new Map(calendario.slice(0, visible).map((item) => [item.dia, item.tipo]));
  return (
    <div className={`calendar ${compact ? 'calendar-compact' : ''}`}>
      {!compact && ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'].map((dia) => <b key={dia}>{dia}</b>)}
      {Array.from({ length: compact ? 28 : 30 }, (_, index) => index + 1).map((dia) => (
        <span key={dia}><small>{dia}</small>{tipos.has(dia) && <i data-kind={tipos.get(dia)}>{tipos.get(dia)}</i>}</span>
      ))}
    </div>
  );
}

