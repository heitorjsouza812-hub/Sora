import { calendario } from '../../data/mock';

export function Calendar({ compact = false }: { compact?: boolean }) {
  const tipos = new Map(calendario.map((item) => [item.dia, item.tipo]));
  return (
    <div className={`calendar ${compact ? 'calendar-compact' : ''}`}>
      {!compact && ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'].map((dia) => <b key={dia}>{dia}</b>)}
      {Array.from({ length: compact ? 28 : 30 }, (_, index) => index + 1).map((dia) => (
        <span key={dia}><small>{dia}</small>{tipos.has(dia) && <i data-kind={tipos.get(dia)}>{tipos.get(dia)}</i>}</span>
      ))}
    </div>
  );
}

