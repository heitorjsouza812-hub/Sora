export function ProgressBar({ value, color }: { value: number; color: string }) {
  return <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={value}><span style={{ width: `${value}%`, background: color, boxShadow: `0 0 18px ${color}66` }} /></div>;
}

