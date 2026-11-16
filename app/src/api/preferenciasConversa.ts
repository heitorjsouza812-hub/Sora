import { api, ErroApi } from './cliente';
export type NivelRaciocinio = 'baixo' | 'medio' | 'alto' | 'extra_alto' | 'maximo';
export interface PreferenciasConversa {
  provedor_id: string | null;
  modelo: string | null;
  raciocinio: 'auto' | NivelRaciocinio;
  permissao: 'perguntar' | 'automatico' | 'total';
}
export const AUTOMATICO: PreferenciasConversa = { provedor_id: null, modelo: null, raciocinio: 'auto', permissao: 'perguntar' };
export function normalizarPreferencias(p: Partial<PreferenciasConversa>): PreferenciasConversa {
  return { provedor_id: p.provedor_id ?? null, modelo: p.modelo ?? null, raciocinio: p.raciocinio ?? 'auto', permissao: p.permissao ?? 'perguntar' };
}
export async function lerPreferencias(caminho: string): Promise<PreferenciasConversa | null> {
  try {
    // A API de bots oferece listagem e PATCH, sem GET individual.
    if (caminho.startsWith('/v1/agentes/')) {
      const bots = await api.get<(PreferenciasConversa & { id: string })[]>('/v1/agentes');
      const bot = bots.find(b => b.id === caminho.split('/').at(-1));
      return bot ? normalizarPreferencias(bot) : null;
    }
    return normalizarPreferencias(await api.get<PreferenciasConversa>(caminho));
  }
  catch (e) { if (e instanceof ErroApi && e.status === 404) return null; throw e; }
}
export async function gravarPreferencias(caminho: string, valor: PreferenciasConversa, confirmar = false): Promise<PreferenciasConversa | null> {
  try { return normalizarPreferencias(await api.patch<PreferenciasConversa>(caminho, { ...valor, ...(confirmar ? { confirmar_total: true } : {}) })); }
  catch (e) { if (e instanceof ErroApi && e.status === 404) return null; throw e; }
}
