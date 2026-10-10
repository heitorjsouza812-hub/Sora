/** Barra de progresso acessível: `label` vira aria-label e aria-valuetext ("Atlas: 55%, pesquisando"). */
export function ProgressBar({ value, color, label, status }: { value: number; color: string; label?: string; status?: string }) {
  const texto = `${label ? `${label}: ` : ''}${value}%${status ? `, ${status.toLowerCase()}` : ''}`;
  return (
    <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={value}
      aria-label={label ? `Progresso de ${label}` : 'Progresso'} aria-valuetext={texto}>
      <span style={{ width: `${value}%`, background: color, boxShadow: `0 0 18px ${color}66` }} />
    </div>
  );
}
