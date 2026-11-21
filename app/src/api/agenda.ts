// Agenda das rotinas e feed .ics (backend: app/api/agenda.py).
import { api } from './cliente';

export interface Prevista { rotina_id: string; agente_id: string; titulo: string; quando: string }
export interface Feita { rotina_id: string; titulo: string; iniciada_em: string; status: 'executando' | 'enviada' | 'silenciosa' | 'falhou'; origem: string }
export interface Agenda { previstas: Prevista[]; feitas: Feita[] }
export interface Feed { ligado: boolean; criado_em: string | null; url: string | null }

export const obterAgenda = (de: Date, ate: Date) =>
  api.get<Agenda>(`/v1/agenda?de=${encodeURIComponent(de.toISOString())}&ate=${encodeURIComponent(ate.toISOString())}`);
export const obterFeed = () => api.get<Feed>('/v1/agenda/feed');
/** Liga ou troca o endereço (o antigo para na hora). A URL só vem aqui. */
export const ligarFeed = () => api.post<Feed>('/v1/agenda/feed');
export const desligarFeed = () => api.delete<void>('/v1/agenda/feed');

/** Primeiro dia (domingo) da grade de 6 semanas que mostra o mês de `mes`. */
export function inicioDaGrade(mes: Date): Date {
  const primeiro = new Date(mes.getFullYear(), mes.getMonth(), 1);
  return new Date(primeiro.getFullYear(), primeiro.getMonth(), 1 - primeiro.getDay());
}

/** Chave local AAAA-MM-DD de uma data (no fuso de quem está vendo). */
export function chaveDoDia(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
