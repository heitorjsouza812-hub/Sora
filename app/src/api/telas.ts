// Rotas das telas ao vivo (navegador e computador do bot). Contrato: .maestri/contrato-etapa5.md (Farol e Farol-2).
// Nenhuma função guarda texto digitado: o texto vai direto ao servidor e some.
import { api, buscarAutenticado } from './cliente';

export interface EstadoComputadorApi { agente_id: string; disponivel: boolean; ligado: boolean; alvo: string; largura: number | null; altura: number | null; janela_ativa: string | null; acao: string | null; atualizado_em: string | null }

/** Marca "estou olhando" por 12 s; o app repete enquanto o painel está visível. */
export const assistirNavegador = (agenteId: string) => api.post<{ expira_em_segundos: number }>(`/v1/agentes/${agenteId}/navegador/assistir`);
export const estadoDoComputador = (agenteId: string) => api.get<EstadoComputadorApi>(`/v1/agentes/${agenteId}/computador`);
export const desligarComputador = (agenteId: string) => api.post<void>(`/v1/agentes/${agenteId}/computador/desligar`);

async function blobDe(caminho: string, signal?: AbortSignal): Promise<string> {
  const r = await buscarAutenticado(caminho, { signal }); return URL.createObjectURL(await r.blob());
}
/** Quadro inteiro da aba (JPEG) como URL de blob; quem chama revoga. 404 = ainda sem quadro. */
export const capturaDaAba = (abaId: string, signal?: AbortSignal) => blobDe(`/v1/navegador/abas/${abaId}/captura`, signal);
export const capturaDoComputador = (agenteId: string, signal?: AbortSignal) => blobDe(`/v1/agentes/${agenteId}/computador/captura`, signal);

export const TECLAS_ABA = ['Enter', 'Tab', 'Escape', 'Backspace', 'Delete', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown'] as const;
const abaUrl = (abaId: string, acao: string) => `/v1/navegador/abas/${abaId}/${acao}`;
export const clicarNaAba = (abaId: string, x: number, y: number, largura: number, altura: number) => api.post<{ enviado: boolean }>(abaUrl(abaId, 'clicar'), { x: Math.round(x), y: Math.round(y), largura: Math.round(largura), altura: Math.round(altura) });
export const digitarNaAba = (abaId: string, texto: string) => api.post<{ enviado: boolean }>(abaUrl(abaId, 'digitar'), { texto: texto.slice(0, 500) });
export const teclaNaAba = (abaId: string, tecla: string) => api.post<{ enviado: boolean }>(abaUrl(abaId, 'tecla'), { tecla });
export const rolarAba = (abaId: string, dy: number) => api.post<{ enviado: boolean }>(abaUrl(abaId, 'rolar'), { dy: Math.max(-5000, Math.min(5000, Math.round(dy))) });

export type TipoNavegadorBot = 'efemero' | 'compartilhado' | 'agente' | 'perfil';
/** Escolhe o navegador do bot. `agente` = perfil só dele (aceito pelo backend desde a etapa 6). */
export const definirNavegadorDoBot = (agenteId: string, tipo: TipoNavegadorBot, perfilId?: string) =>
  api.put<{ agente_id: string; tipo: TipoNavegadorBot; perfil_id: string | null; perfil_nome: string | null }>(`/v1/agentes/${agenteId}/navegador`, { tipo, ...(perfilId ? { perfil_id: perfilId } : {}) });
