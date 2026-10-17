import { useEffect, useSyncExternalStore } from 'react';
import { api, mensagemDeErro } from '../api/cliente';
import { recarregarSessao } from './sessao';

export type ProvedorModeloId = 'openai' | 'anthropic' | 'gemini' | 'groq' | 'xai' | 'deepseek' | 'mistral' | 'openrouter' | 'ollama' | 'openai-compativel';
export type TipoProvedorApi = 'groq' | 'openai' | 'anthropic' | 'google' | 'openrouter' | 'compativel_openai' | 'ollama';
export type PrioridadeModelo = 'custo' | 'velocidade' | 'qualidade';
export type NivelModelo = 'N1' | 'N2' | 'N3' | 'especial';
export type StatusConexao = 'nao-conectado' | 'conectado';

export interface ProvedorApi {
  id: string;
  tipo: TipoProvedorApi;
  base_url: string | null;
  chave_final: string | null;
  teto_mensal_usd: string | number | null;
  gasto_mes_usd: string | number;
}

export interface ModeloConfigurado {
  id: string;
  provedor_id: string;
  modelo: string;
  nome_exibicao?: string | null;
  nivel: NivelModelo;
  capacidades: string[];
  contexto: number;
  preco_entrada: string | number | null;
  preco_saida: string | number | null;
  velocidade_tps: number | null;
  ativo: boolean;
}

/** Nome voltado à interface; o identificador técnico completo continua em `modelo`. */
export function nomeAmigavelDoModelo(modelo: Pick<ModeloConfigurado, 'modelo' | 'nome_exibicao'>): string {
  const nomeExibicao = modelo.nome_exibicao?.trim();
  if (nomeExibicao) return nomeExibicao;
  const separador = modelo.modelo.indexOf('/');
  return separador >= 0 && separador < modelo.modelo.length - 1
    ? modelo.modelo.slice(separador + 1)
    : modelo.modelo;
}

export interface ConfiguracaoProvedor {
  status: StatusConexao;
  conexao: ProvedorApi | null;
  modelos: ModeloConfigurado[];
}

export interface EscolhaModelo { provedor: ProvedorModeloId; modelo: string }
interface PreferenciasLocais {
  versao: 2;
  padraoSora: EscolhaModelo | null;
  padraoNovosAgentes: EscolhaModelo | null;
  modelosPorAgente: Record<string, EscolhaModelo>;
}
export interface EstadoModelos extends PreferenciasLocais {
  provedores: Record<ProvedorModeloId, ConfiguracaoProvedor>;
  modelos: ModeloConfigurado[];
  prioridade: PrioridadeModelo;
  carregando: boolean;
  carregado: boolean;
  erro: string | null;
}
export interface DefinicaoProvedor {
  id: ProvedorModeloId;
  tipoApi: TipoProvedorApi;
  nome: string;
  descricao: string;
  prefixo?: string;
  pedeChave: boolean;
  pedeUrl?: boolean;
  baseUrl?: string;
  iconePlugin?: string;
}

export const PROVEDORES_MODELO: DefinicaoProvedor[] = [
  { id: 'openai', tipoApi: 'openai', nome: 'OpenAI', descricao: 'GPT para conversa, raciocínio e multimodal.', prefixo: 'sk-', pedeChave: true, iconePlugin: 'ChatGPT' },
  { id: 'anthropic', tipoApi: 'anthropic', nome: 'Anthropic', descricao: 'Família Claude para escrita e raciocínio.', prefixo: 'sk-ant-', pedeChave: true, iconePlugin: 'Anthropic' },
  { id: 'gemini', tipoApi: 'google', nome: 'Google Gemini', descricao: 'Modelos multimodais do Google.', prefixo: 'AIza', pedeChave: true, iconePlugin: 'Gemini' },
  { id: 'groq', tipoApi: 'groq', nome: 'Groq', descricao: 'Inferência rápida para modelos abertos.', prefixo: 'gsk_', pedeChave: true },
  { id: 'xai', tipoApi: 'compativel_openai', nome: 'xAI (Grok)', descricao: 'Modelos Grok pela API compatível com OpenAI.', prefixo: 'xai-', pedeChave: true, pedeUrl: true, baseUrl: 'https://api.x.ai/v1' },
  { id: 'deepseek', tipoApi: 'compativel_openai', nome: 'DeepSeek', descricao: 'Modelos de raciocínio e código.', prefixo: 'sk-', pedeChave: true, pedeUrl: true, baseUrl: 'https://api.deepseek.com/v1' },
  { id: 'mistral', tipoApi: 'compativel_openai', nome: 'Mistral', descricao: 'Modelos abertos e comerciais da Mistral AI.', pedeChave: true, pedeUrl: true, baseUrl: 'https://api.mistral.ai/v1' },
  { id: 'openrouter', tipoApi: 'openrouter', nome: 'OpenRouter', descricao: 'Acesso unificado a modelos de vários provedores.', prefixo: 'sk-or-', pedeChave: true },
  { id: 'ollama', tipoApi: 'ollama', nome: 'Ollama', descricao: 'Modelos executados localmente neste dispositivo.', pedeChave: false, pedeUrl: true, baseUrl: 'http://localhost:11434' },
  { id: 'openai-compativel', tipoApi: 'compativel_openai', nome: 'Compatível com OpenAI', descricao: 'Servidor próprio com API no formato OpenAI.', pedeChave: true, pedeUrl: true },
];

const CHAVE_STORAGE = 'sora.modelos.v1';
const definicoes = Object.fromEntries(PROVEDORES_MODELO.map(p => [p.id, p])) as Record<ProvedorModeloId, DefinicaoProvedor>;
const preferenciasIniciais = (): PreferenciasLocais => ({ versao: 2, padraoSora: null, padraoNovosAgentes: null, modelosPorAgente: {} });

function ehEscolha(valor: unknown): valor is EscolhaModelo {
  if (!valor || typeof valor !== 'object') return false;
  const escolha = valor as Partial<EscolhaModelo>;
  return typeof escolha.provedor === 'string' && escolha.provedor in definicoes && typeof escolha.modelo === 'string';
}

/** Migra formatos antigos regravando somente preferências sem segredo. */
function carregarPreferencias(): PreferenciasLocais {
  const base = preferenciasIniciais();
  try {
    const bruto = localStorage.getItem(CHAVE_STORAGE);
    if (!bruto) return base;
    const salvo = JSON.parse(bruto) as Record<string, unknown>;
    const modelosPorAgente = salvo.modelosPorAgente && typeof salvo.modelosPorAgente === 'object'
      ? Object.fromEntries(Object.entries(salvo.modelosPorAgente as Record<string, unknown>).filter(([, valor]) => ehEscolha(valor))) as Record<string, EscolhaModelo>
      : {};
    const seguro: PreferenciasLocais = {
      versao: 2,
      padraoSora: ehEscolha(salvo.padraoSora) ? salvo.padraoSora : null,
      padraoNovosAgentes: ehEscolha(salvo.padraoNovosAgentes) ? salvo.padraoNovosAgentes : null,
      modelosPorAgente,
    };
    localStorage.setItem(CHAVE_STORAGE, JSON.stringify(seguro));
    return seguro;
  } catch {
    try { localStorage.setItem(CHAVE_STORAGE, JSON.stringify(base)); } catch { /* somente memória */ }
    return base;
  }
}

function provedoresVazios(): Record<ProvedorModeloId, ConfiguracaoProvedor> {
  return Object.fromEntries(PROVEDORES_MODELO.map(p => [p.id, { status: 'nao-conectado', conexao: null, modelos: [] }])) as unknown as Record<ProvedorModeloId, ConfiguracaoProvedor>;
}

const locais = typeof window === 'undefined' ? preferenciasIniciais() : carregarPreferencias();
let estado: EstadoModelos = { ...locais, provedores: provedoresVazios(), modelos: [], prioridade: 'custo', carregando: false, carregado: false, erro: null };
const ouvintes = new Set<() => void>();
const assinar = (fn: () => void) => { ouvintes.add(fn); return () => { ouvintes.delete(fn); }; };
export const lerModelos = () => estado;

export function useModelos() {
  const atual = useSyncExternalStore(assinar, lerModelos, lerModelos);
  useEffect(() => { if (!estado.carregado && !estado.carregando) void carregarModelos().catch(() => {}); }, []);
  return atual;
}

function publicar(patch: Partial<EstadoModelos>) {
  estado = { ...estado, ...patch };
  ouvintes.forEach(fn => fn());
}

function salvarPreferencias(patch: Partial<PreferenciasLocais>) {
  const preferencias: PreferenciasLocais = {
    versao: 2,
    padraoSora: patch.padraoSora === undefined ? estado.padraoSora : patch.padraoSora,
    padraoNovosAgentes: patch.padraoNovosAgentes === undefined ? estado.padraoNovosAgentes : patch.padraoNovosAgentes,
    modelosPorAgente: patch.modelosPorAgente ?? estado.modelosPorAgente,
  };
  publicar(preferencias);
  try { localStorage.setItem(CHAVE_STORAGE, JSON.stringify(preferencias)); } catch { /* somente memória */ }
}

const normalizarUrl = (url: string | null | undefined) => (url ?? '').replace(/\/+$/, '').toLowerCase();
export function idVisualDoProvedor(provedor: ProvedorApi): ProvedorModeloId {
  if (provedor.tipo === 'google') return 'gemini';
  if (provedor.tipo !== 'compativel_openai') return provedor.tipo as ProvedorModeloId;
  const url = normalizarUrl(provedor.base_url);
  return PROVEDORES_MODELO.find(p => p.tipoApi === 'compativel_openai' && p.baseUrl && normalizarUrl(p.baseUrl) === url)?.id ?? 'openai-compativel';
}

function montarProvedores(conexoes: ProvedorApi[], modelos: ModeloConfigurado[]) {
  const resultado = provedoresVazios();
  for (const conexao of conexoes) {
    const id = idVisualDoProvedor(conexao);
    if (!resultado[id].conexao) resultado[id] = { status: 'conectado', conexao, modelos: modelos.filter(m => m.provedor_id === conexao.id) };
  }
  return resultado;
}

interface ContaPreferencias { prioridade: PrioridadeModelo }
export async function carregarModelos(): Promise<void> {
  if (estado.carregando) return;
  publicar({ carregando: true, erro: null });
  try {
    const [provedores, modelos, conta] = await Promise.all([
      api.get<ProvedorApi[]>('/v1/provedores'), api.get<ModeloConfigurado[]>('/v1/modelos'), api.get<ContaPreferencias>('/v1/eu'),
    ]);
    publicar({ provedores: montarProvedores(provedores, modelos), modelos, prioridade: conta.prioridade, carregando: false, carregado: true });
  } catch (erro) {
    publicar({ carregando: false, carregado: false, erro: mensagemDeErro(erro) });
    throw erro;
  }
}

async function recarregarTudo() {
  publicar({ carregado: false });
  await carregarModelos();
  await recarregarSessao();
}

export interface ConectarProvedorEntrada { chave?: string; baseUrl?: string }
export async function conectarProvedor(id: ProvedorModeloId, entrada: ConectarProvedorEntrada): Promise<void> {
  const definicao = definicoes[id];
  await api.post('/v1/provedores', { tipo: definicao.tipoApi, chave: entrada.chave?.trim() || undefined, base_url: entrada.baseUrl?.trim() || definicao.baseUrl || undefined });
  await recarregarTudo();
}

export async function atualizarProvedor(id: ProvedorModeloId, patch: { chave?: string; tetoMensalUsd?: number | null }): Promise<void> {
  const conexao = estado.provedores[id].conexao;
  if (!conexao) throw new Error('Provedor não conectado.');
  const corpo: Record<string, unknown> = {};
  if (patch.chave !== undefined) corpo.chave = patch.chave.trim();
  if ('tetoMensalUsd' in patch) corpo.teto_mensal_usd = patch.tetoMensalUsd;
  await api.patch(`/v1/provedores/${conexao.id}`, corpo);
  await recarregarTudo();
}

export async function desconectarProvedor(id: ProvedorModeloId): Promise<void> {
  const conexao = estado.provedores[id].conexao;
  if (!conexao) return;
  await api.delete(`/v1/provedores/${conexao.id}`);
  await recarregarTudo();
}

export async function desconectarTodosProvedores(): Promise<void> {
  const ids = [...new Set(Object.values(estado.provedores).map(p => p.conexao?.id).filter((id): id is string => !!id))];
  await Promise.all(ids.map(id => api.delete(`/v1/provedores/${id}`)));
  await recarregarTudo();
}

export async function atualizarModelo(id: string, patch: { nivel?: NivelModelo; ativo?: boolean }): Promise<void> {
  const atualizado = await api.patch<ModeloConfigurado>(`/v1/modelos/${id}`, patch);
  const modelos = estado.modelos.map(modelo => modelo.id === id ? atualizado : modelo);
  publicar({ modelos, provedores: montarProvedores(Object.values(estado.provedores).flatMap(p => p.conexao ? [p.conexao] : []), modelos) });
}

export async function definirPrioridade(prioridade: PrioridadeModelo): Promise<void> {
  await api.patch('/v1/preferencias', { prioridade });
  publicar({ prioridade });
  await recarregarSessao();
}

export function definirPadraoSora(escolha: EscolhaModelo | null) { salvarPreferencias({ padraoSora: escolha }); }
export function definirPadraoNovosAgentes(escolha: EscolhaModelo | null) { salvarPreferencias({ padraoNovosAgentes: escolha }); }
export function modeloDoAgente(id: string) { return estado.modelosPorAgente[id] ?? estado.padraoNovosAgentes; }
export function definirModeloAgente(id: string, provedor: ProvedorModeloId, modelo: string) { salvarPreferencias({ modelosPorAgente: { ...estado.modelosPorAgente, [id]: { provedor, modelo } } }); }

export function modelosAtivos(estadoAtual = estado) {
  return estadoAtual.modelos.filter(modelo => modelo.ativo).map(modelo => {
    const conexao = Object.values(estadoAtual.provedores).find(p => p.conexao?.id === modelo.provedor_id)?.conexao;
    const provedor = conexao ? idVisualDoProvedor(conexao) : null;
    return provedor ? { provedor, modelo, definicao: definicoes[provedor] } : null;
  }).filter((item): item is { provedor: ProvedorModeloId; modelo: ModeloConfigurado; definicao: DefinicaoProvedor } => item !== null);
}

if (typeof window !== 'undefined') window.addEventListener('storage', ev => { if (ev.key === CHAVE_STORAGE) publicar(carregarPreferencias()); });
export function _reiniciarModelosParaTestes() {
  const preferencias = typeof window === 'undefined' ? preferenciasIniciais() : carregarPreferencias();
  estado = { ...preferencias, provedores: provedoresVazios(), modelos: [], prioridade: 'custo', carregando: false, carregado: false, erro: null };
  ouvintes.clear();
}
