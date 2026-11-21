// "Ensinar uma tarefa" (Onda 3): com a aba do bot assumida, o que o usuário faz vira passos de uma
// habilidade. O servidor devolve só o rascunho; quem salva é o usuário, depois de ler.
import { api } from './cliente';

export interface Gravacao { gravando: boolean; passos: string[] }
export interface RascunhoHabilidade { nome: string; descricao: string; corpo: string; passos: number }

const rota = (abaId: string) => `/v1/navegador/abas/${encodeURIComponent(abaId)}/ensinar`;
export const comecarAEnsinar = (abaId: string) => api.post<Gravacao>(rota(abaId));
export const verGravacao = (abaId: string) => api.get<Gravacao>(rota(abaId));
export const concluirEnsino = (abaId: string, objetivo: string) => api.post<RascunhoHabilidade>(`${rota(abaId)}/concluir`, { objetivo });
export const cancelarEnsino = (abaId: string) => api.delete<void>(rota(abaId));
