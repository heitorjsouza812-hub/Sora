// Rotas de Configurações da etapa 4 (contrato em .maestri/contrato-etapa4.md): memória (Âncora),
// rotinas, conectores MCP, habilidades e Telegram (Relógio). Sem estado global: cada seção carrega e recarrega a sua lista.
import { api, ehErroApi, mensagemDeErro } from '../api/cliente';

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

export interface Habilidade { id: string; nome: string; descricao: string; corpo: string; origem: string; criada_em: string; atualizada_em: string }
export const listarHabilidades = () => api.get<Habilidade[]>('/v1/habilidades');
export const criarHabilidade = (h: { nome: string; descricao: string; corpo: string }) => api.post<Habilidade>('/v1/habilidades', h);
export const alterarHabilidade = (id: string, h: { descricao?: string; corpo?: string }) => api.patch<Habilidade>(`/v1/habilidades/${id}`, h);
export const apagarHabilidade = (id: string) => api.delete<void>(`/v1/habilidades/${id}`);

export interface CanalExterno { canal: 'telegram'; disponivel: boolean; vinculos: { id: string; chat_id: string; criado_em: string }[] }
export interface CodigoVinculo { codigo: string; expira_em_segundos: number; comando: string }
export const listarCanaisExternos = () => api.get<CanalExterno[]>('/v1/canais');
export const gerarVinculoTelegram = () => api.post<CodigoVinculo>('/v1/canais/telegram/vinculo');
export const removerVinculoTelegram = (id: string) => api.delete<void>(`/v1/canais/telegram/vinculos/${id}`);

// ── Pendências do agente (Âncora): lista própria do agente, não acorda ninguém ────────────
export type StatusPendencia = 'aberta' | 'estacionada' | 'concluida';
export interface PendenciaAgente { id: string; agente_id: string; titulo: string; notas: string; status: StatusPendencia; criada_em: string; atualizada_em: string }
export const listarPendenciasDoAgente = (agenteId: string) => api.get<PendenciaAgente[]>(`/v1/agentes/${agenteId}/pendencias?incluir_concluidas=true`);
export const criarPendenciaDoAgente = (agenteId: string, p: { titulo: string; notas?: string; status?: 'aberta' | 'estacionada' }) => api.post<PendenciaAgente>(`/v1/agentes/${agenteId}/pendencias`, p);
export const alterarPendenciaDoAgente = (id: string, patch: { titulo?: string; notas?: string; status?: StatusPendencia }) => api.patch<PendenciaAgente>(`/v1/pendencias/${id}`, patch);
export const apagarPendenciaDoAgente = (id: string) => api.delete<void>(`/v1/pendencias/${id}`);

export const LIMITE_PENDENCIAS_ABERTAS = 100;
const MSG_LIMITE = `Este agente já tem ${LIMITE_PENDENCIAS_ABERTAS} pendências abertas. Conclua ou apague alguma antes de criar outra.`;
/** O servidor responde 409 com um texto genérico; aqui o aviso diz o limite e o que fazer. */
export const mensagemPendencia = (e: unknown): string => ehErroApi(e) && e.status === 409 ? MSG_LIMITE : mensagemDeErro(e);

// ── Perfis do navegador (Leme): login salvo e domínios aprovados; nunca voltam cookies ────
export type TipoPerfil = 'compartilhado' | 'agente' | 'nomeado';
export interface PerfilNavegador { perfil_id: string; nome: string; tipo: TipoPerfil; dominios_aprovados: string[]; criado_em: string; atualizado_em: string }
export const listarPerfisNavegador = () => api.get<PerfilNavegador[]>('/v1/navegador/perfis');
export const apagarPerfilNavegador = (id: string) => api.delete<void>(`/v1/navegador/perfis/${id}`);
export const revogarDominioPerfil = (id: string, dominio: string) => api.delete<void>(`/v1/navegador/perfis/${id}/dominios/${encodeURIComponent(dominio)}`);

export const criarPerfilNavegador = (nome: string) => api.post<PerfilNavegador>('/v1/navegador/perfis', { nome });
/** Abre uma aba já assumida pelo usuário no perfil, para ele entrar na conta; devolve o estado da aba. */
export const abrirPerfilNavegador = (id: string, url: string, agenteId?: string) =>
  api.post<Record<string, unknown>>(`/v1/navegador/perfis/${id}/abrir`, { url, ...(agenteId ? { agente_id: agenteId } : {}) });
export type TipoNavegadorAgente = 'efemero' | 'compartilhado' | 'perfil' | 'agente';
export interface NavegadorDoAgente { agente_id: string; tipo: TipoNavegadorAgente; perfil_id: string | null; perfil_nome: string | null }
export const lerNavegadorDoAgente = (agenteId: string) => api.get<NavegadorDoAgente>(`/v1/agentes/${agenteId}/navegador`);
export const definirNavegadorDoAgente = (agenteId: string, tipo: Exclude<TipoNavegadorAgente, 'agente'>, perfilId?: string) =>
  api.put<NavegadorDoAgente>(`/v1/agentes/${agenteId}/navegador`, { tipo, ...(perfilId ? { perfil_id: perfilId } : {}) });

/** Mensagens próprias de perfis: o 409 do servidor pode ser nome repetido ou limite; o 503 é o navegador fora do ar. */
export function mensagemPerfil(e: unknown, aoCriar = false): string {
  if (ehErroApi(e) && e.status === 409 && aoCriar) return 'Já existe um perfil com esse nome ou você chegou ao limite de perfis. Escolha outro nome ou apague um perfil.';
  if (ehErroApi(e) && e.status === 503) return 'O navegador da Sora não respondeu agora. Tente de novo em instantes.';
  return mensagemDeErro(e);
}
