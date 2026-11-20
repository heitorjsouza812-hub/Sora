// "Relatar problema": POST/GET/DELETE /v1/relatos. O diagnóstico vai já sem dado pessoal
// (src/diagnostico) e o servidor mascara de novo antes de gravar.
import { api } from './cliente';
import type { Diagnostico } from '../diagnostico';

export interface RelatoEnviado { id: string; resumo: string; com_diagnostico: boolean; criado_em: string }

export const enviarRelato = (texto: string, diagnostico: Diagnostico | null) =>
  api.post<RelatoEnviado>('/v1/relatos', { texto: texto.trim(), diagnostico });

export const listarRelatos = () => api.get<RelatoEnviado[]>('/v1/relatos');

export const retirarRelato = (id: string) => api.delete<void>(`/v1/relatos/${encodeURIComponent(id)}`);
