// Chaves extras por conexão e modelos reserva da conta (migração 0019 do backend).
// A chave inteira só vai ao servidor; de volta vêm só os 4 últimos caracteres.
import { api } from './cliente';

export interface ChaveExtra { id: string; chave_final: string | null; criado_em: string }
export interface ItemReserva { provedor_id: string; modelo: string }

/** Até 4 chaves extras por conexão; até 3 modelos reserva por conta (iguais ao backend). */
export const MAX_CHAVES_EXTRAS = 4;
export const MAX_RESERVAS = 3;

const rotaChaves = (provedorId: string) => `/v1/provedores/${encodeURIComponent(provedorId)}/chaves`;

export const listarChavesExtras = (provedorId: string) => api.get<ChaveExtra[]>(rotaChaves(provedorId));

export const adicionarChaveExtra = (provedorId: string, chave: string) =>
  api.post<ChaveExtra>(rotaChaves(provedorId), { chave: chave.trim() });

export const removerChaveExtra = (provedorId: string, chaveId: string) =>
  api.delete<void>(`${rotaChaves(provedorId)}/${encodeURIComponent(chaveId)}`);

export const obterReservas = () => api.get<ItemReserva[]>('/v1/modelos-reserva');

export const definirReservas = (itens: ItemReserva[]) => api.put<ItemReserva[]>('/v1/modelos-reserva', { itens });
