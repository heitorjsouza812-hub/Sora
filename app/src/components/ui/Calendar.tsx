const calendario = [
  { dia: 2, tipo: 'Post' }, { dia: 4, tipo: 'Story' }, { dia: 6, tipo: 'Reels' },
  { dia: 7, tipo: 'Post' }, { dia: 9, tipo: 'Story' }, { dia: 11, tipo: 'Post' },
  { dia: 13, tipo: 'Reels' }, { dia: 16, tipo: 'Post' }, { dia: 18, tipo: 'Story' },
  { dia: 20, tipo: 'Post' }, { dia: 23, tipo: 'Reels' }, { dia: 27, tipo: 'Post' },
];

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

