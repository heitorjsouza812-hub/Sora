// Rotas de Configurações da etapa 4 (contrato em .maestri/contrato-etapa4.md): memória (Âncora),
// rotinas, conectores MCP, habilidades e Telegram (Relógio). Sem estado global: cada seção carrega e recarrega a sua lista.
import { api } from '../api/cliente';

export interface Memoria { id: string; agente_id: string | null; conteudo: string; tipo: string; origem: string; travada: boolean; criada_em: string }
export const listarMemorias = () => api.get<Memoria[]>('/v1/memorias');
export const criarMemoria = (conteudo: string, agenteId?: string) => api.post<Memoria>('/v1/memorias', { conteudo, ...(agenteId ? { agente_id: agenteId } : {}) });
export const apagarMemoria = (id: string) => api.delete<void>(`/v1/memorias/${id}`);

export interface Rotina {
  id: string; agente_id: string | null; conversa_id: string | null; titulo: string; pedido: string; tipo: 'unico' | 'cron' | 'intervalo'; expressao: string | null; fuso: string | null;
  proxima_execucao: string | null; ultima_execucao: string | null; silencioso: boolean; ativa: boolean; ultimo_status: string | null; criada_em: string;
}
export interface ExecucaoRotina { id: string; rotina_id: string; iniciada_em: string; concluida_em: string | null; status: 'executando' | 'enviada' | 'silenciosa' | 'falhou'; resumo: string | null; erro: string | null; mensagem_id: string | null }
export interface NovaRotina { agente_id?: string; titulo: string; pedido: string; silencioso?: boolean; fuso?: string; cron?: string; a_cada?: number; unidade?: 'minutos' | 'horas' | 'dias'; daqui_minutos?: number }
export const listarRotinas = () => api.get<Rotina[]>('/v1/rotinas');
export const criarRotina = (r: NovaRotina) => api.post<Rotina>('/v1/rotinas', r);
export const alterarRotina = (id: string, patch: Partial<Pick<Rotina, 'titulo' | 'pedido' | 'silencioso' | 'ativa'>>) => api.patch<Rotina>(`/v1/rotinas/${id}`, patch);
export const apagarRotina = (id: string) => api.delete<void>(`/v1/rotinas/${id}`);
export const executarRotina = (id: string) => api.post<{ execucao_id: string }>(`/v1/rotinas/${id}/executar`);
export const execucoesDaRotina = (id: string) => api.get<ExecucaoRotina[]>(`/v1/rotinas/${id}/execucoes?limite=20`);

export interface Conector { id: string; nome: string; url: string; ativo: boolean; tem_cabecalhos: boolean; estado: 'desconhecido' | 'ok' | 'erro'; n_ferramentas: number; ultimo_erro: string | null; criado_em: string }
export const listarConectores = () => api.get<Conector[]>('/v1/conectores');
export const criarConector = (c: { nome: string; url: string; cabecalhos?: Record<string, string> }) => api.post<Conector>('/v1/conectores', c);
export const alterarConector = (id: string, ativo: boolean) => api.patch<Conector>(`/v1/conectores/${id}`, { ativo });
export const apagarConector = (id: string) => api.delete<void>(`/v1/conectores/${id}`);
export const testarConector = (id: string) => api.post<{ ok: boolean; ferramentas: string[]; erro: string | null }>(`/v1/conectores/${id}/testar`);

export interface Habilidade { id: string; nome: string; descricao: string; conteudo: string; origem: string; criada_em: string; atualizada_em: string }
export const listarHabilidades = () => api.get<Habilidade[]>('/v1/habilidades');
export const criarHabilidade = (h: { nome: string; descricao: string; conteudo: string }) => api.post<Habilidade>('/v1/habilidades', h);
export const alterarHabilidade = (id: string, h: { descricao?: string; conteudo?: string }) => api.patch<Habilidade>(`/v1/habilidades/${id}`, h);
export const apagarHabilidade = (id: string) => api.delete<void>(`/v1/habilidades/${id}`);

export interface CanalExterno { canal: 'telegram'; disponivel: boolean; vinculos: { id: string; chat_id: string; criado_em: string }[] }
export interface CodigoVinculo { codigo: string; expira_em_segundos: number; comando: string }
export const listarCanaisExternos = () => api.get<CanalExterno[]>('/v1/canais');
export const gerarVinculoTelegram = () => api.post<CodigoVinculo>('/v1/canais/telegram/vinculo');
export const removerVinculoTelegram = (id: string) => api.delete<void>(`/v1/canais/telegram/vinculos/${id}`);
