export function urlPublica(url?: string): string | undefined {
  try { const u = new URL(url ?? ''); return ['http:', 'https:'].includes(u.protocol) && !u.username && !u.password ? u.href : undefined; } catch { return undefined; }
}
export const idFonte = (mensagemId: string, n: number) => `fonte-${encodeURIComponent(mensagemId)}-${n}`;

