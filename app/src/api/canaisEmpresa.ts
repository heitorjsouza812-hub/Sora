import { api } from './cliente';

export const RAIZ = '/v1/canais-empresa';
export type CanalEmpresa = 'slack' | 'whatsapp';
export interface ConexaoEmpresa {
  canal: CanalEmpresa; configurada: boolean; id?: string; rotulo: string; ativa: boolean;
  config: Record<string, unknown>; segredos_definidos: Record<string, boolean>;
  canais_escolhidos: string[]; webhook_caminho?: string | null;
  ultimo_teste_ok?: boolean | null; ultimo_teste_detalhe?: string | null; escopos_slack: string[];
}
export interface ClienteResumo {
  id: string; canal: CanalEmpresa; nome: string; id_externo: string; papel: string;
  ultima_mensagem_em: string | null; total_fatos: number;
}
export const TIPOS_FATO = { preferencia: 'Preferência', pedido: 'Pedido', promessa: 'Promessa', prazo: 'Prazo', reclamacao: 'Reclamação', dado_de_contato: 'Contato' } as const;
export interface FatoCliente {
  id: string; tipo: keyof typeof TIPOS_FATO; texto: string; data_referencia: string | null;
  origem_canal: string; origem_link: string | null; origem_externo_id: string | null; editado: boolean; criado_em: string;
}
export interface FichaCliente extends ClienteResumo { fatos: FatoCliente[] }
export const CATEGORIAS = { faq: 'FAQ', produto: 'Produtos e preços', politica: 'Políticas', processo: 'Processos', tom_de_voz: 'Tom de voz', objecao: 'Objeções' } as const;
export interface ConhecimentoEmpresa {
  id: string; categoria: keyof typeof CATEGORIAS; titulo: string; conteudo: string; ocorrencias: number;
  contraditorio: boolean; editado: boolean; anteriores: { conteudo: string; em: string }[];
  origens: { canal: string; mensagem_id: string; externo_id: string; link?: string; em: string }[];
  primeira_em: string; ultima_em: string;
}
export interface SugestaoEmpresa {
  id: string; agente_id: string; tipo: string; titulo: string; motivo: string; texto: string;
  habilidade_nome: string | null; conhecimento_ids: string[]; status: string; aprovacao_id: string | null;
  criada_em: string; decidida_em: string | null; desfeita_em: string | null;
}
export interface AutorizacaoEmpresa { alvo_tipo: 'agente' | 'grupo'; alvo_id: string; escopos: ('clientes' | 'conhecimento')[] }
export interface PreferenciasEmpresa { retencao_dias: number; sugestoes_intervalo_dias: number; ultima_analise_em: string | null }
export interface CanalSlack { id: string; nome: string; privado: boolean }
export const canaisEmpresa = {
  conexoes: (signal?: AbortSignal) => api.get<ConexaoEmpresa[]>(`${RAIZ}/conexoes`, { signal }),
  salvarConexao: (canal: CanalEmpresa, dados: { segredos: Record<string, string>; config: Record<string, unknown> }) => api.put<ConexaoEmpresa>(`${RAIZ}/conexoes/${canal}`, dados),
  testar: (canal: CanalEmpresa) => api.post<{ ok: boolean; detalhe: string; avisos: string[] }>(`${RAIZ}/conexoes/${canal}/testar`),
  canaisSlack: () => api.get<CanalSlack[]>(`${RAIZ}/conexoes/slack/canais-disponiveis`),
  escolher: (canal: CanalEmpresa, canais: string[]) => api.put<ConexaoEmpresa>(`${RAIZ}/conexoes/${canal}/canais`, { canais }),
  preferencias: (signal?: AbortSignal) => api.get<PreferenciasEmpresa>(`${RAIZ}/preferencias`, { signal }),
  salvarPreferencias: (dados: Partial<PreferenciasEmpresa>) => api.put<PreferenciasEmpresa>(`${RAIZ}/preferencias`, dados),
  clientes: (busca: string, pagina: number, signal?: AbortSignal) => api.get<ClienteResumo[]>(`${RAIZ}/clientes?${new URLSearchParams({ busca, limite: '50', deslocamento: String(pagina * 50) })}`, { signal }),
  ficha: (id: string, signal?: AbortSignal) => api.get<FichaCliente>(`${RAIZ}/clientes/${id}`, { signal }),
  apagarCliente: (id: string) => api.delete(`${RAIZ}/clientes/${id}`),
  editarFato: (id: string, dados: Pick<FatoCliente, 'texto' | 'tipo' | 'data_referencia'> & { limpar_data: boolean }) => api.patch<FatoCliente>(`${RAIZ}/fatos/${id}`, dados),
  apagarFato: (id: string) => api.delete(`${RAIZ}/fatos/${id}`),
  conhecimento: (busca: string, categoria: string, pagina: number, signal?: AbortSignal) => api.get<ConhecimentoEmpresa[]>(`${RAIZ}/conhecimento?${new URLSearchParams({ busca, ...(categoria ? { categoria } : {}), limite: '50', deslocamento: String(pagina * 50) })}`, { signal }),
  editarConhecimento: (id: string, dados: Pick<ConhecimentoEmpresa, 'titulo' | 'conteudo' | 'categoria'>) => api.patch<ConhecimentoEmpresa>(`${RAIZ}/conhecimento/${id}`, dados),
  apagarConhecimento: (id: string) => api.delete(`${RAIZ}/conhecimento/${id}`),
  sugestoes: (signal?: AbortSignal) => api.get<SugestaoEmpresa[]>(`${RAIZ}/sugestoes`, { signal }),
  editarSugestao: (id: string, texto: string) => api.patch<SugestaoEmpresa>(`${RAIZ}/sugestoes/${id}`, { texto }),
  decidirSugestao: (id: string, acao: 'aplicar' | 'descartar' | 'desfazer') => api.post<SugestaoEmpresa>(`${RAIZ}/sugestoes/${id}/${acao}`),
  autorizacoes: (signal?: AbortSignal) => api.get<AutorizacaoEmpresa[]>(`${RAIZ}/autorizacoes`, { signal }),
  autorizar: (dados: AutorizacaoEmpresa) => api.put<AutorizacaoEmpresa>(`${RAIZ}/autorizacoes`, dados),
};
