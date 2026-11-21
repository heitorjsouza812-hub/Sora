// Webhook das rotinas (backend: app/api/ganchos.py). O segredo só vem na criação ou na troca.
import { api } from './cliente';

export interface Gancho { url: string; ativo: boolean; tipos_evento: string[]; criado_em: string; ultimo_recebido_em: string | null }
export interface GanchoCriado extends Gancho { segredo: string }
export interface EntregaGancho { id: string; tipo_evento: string | null; status: 'aceita' | 'ignorada'; tamanho: number; execucao_id: string | null; recebida_em: string }

const rota = (rotinaId: string) => `/v1/rotinas/${encodeURIComponent(rotinaId)}/gancho`;

/** `null` quando a rotina ainda não tem webhook. */
export async function obterGancho(rotinaId: string): Promise<Gancho | null> {
  try { return await api.get<Gancho>(rota(rotinaId)); }
  catch (erro) { if ((erro as { status?: number }).status === 404) return null; throw erro; }
}
/** Liga o webhook ou troca o segredo (o antigo para de valer na hora). */
export const criarGancho = (rotinaId: string, tiposEvento?: string[]) => api.post<GanchoCriado>(rota(rotinaId), tiposEvento ? { tipos_evento: tiposEvento } : {});
export const alterarGancho = (rotinaId: string, patch: { ativo?: boolean; tipos_evento?: string[] }) => api.patch<Gancho>(rota(rotinaId), patch);
export const apagarGancho = (rotinaId: string) => api.delete<void>(rota(rotinaId));
export const testarGancho = (rotinaId: string) => api.post<{ status: string; execucao_id: string | null }>(`${rota(rotinaId)}/teste`);
export const entregasDoGancho = (rotinaId: string) => api.get<EntregaGancho[]>(`${rota(rotinaId)}/entregas`);

/** "pedido.pago, pedido.cancelado" → lista sem vazios nem repetidos. */
export function lerTipos(texto: string): string[] {
  return [...new Set(texto.split(',').map(t => t.trim()).filter(Boolean))];
}
