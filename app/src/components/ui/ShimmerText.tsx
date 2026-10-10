export function ShimmerText({ children, className = '' }: { children: string; className?: string }) {
  return <span className={`shimmer ${className}`}>{children}</span>;
}

