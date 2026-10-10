import { useSyncExternalStore } from 'react';

export type ProvedorModeloId = 'openai' | 'anthropic' | 'gemini' | 'xai' | 'deepseek' | 'mistral' | 'openrouter' | 'ollama' | 'openai-compativel';
export type StatusConexao = 'nao-conectado' | 'conectado' | 'erro';

export interface ModeloConfigurado { id: string; habilitado: boolean }
export interface ConfiguracaoProvedor {
  chave?: string;
  urlBase?: string;
  nome?: string;
  status: StatusConexao;
  modelos: ModeloConfigurado[];
}
export interface EscolhaModelo { provedor: ProvedorModeloId; modelo: string }
export interface EstadoModelos {
  versao: 1;
  provedores: Record<ProvedorModeloId, ConfiguracaoProvedor>;
  padraoSora: EscolhaModelo | null;
  padraoNovosAgentes: EscolhaModelo | null;
  modelosPorAgente: Record<string, EscolhaModelo>;
}
export interface DefinicaoProvedor {
  id: ProvedorModeloId;
  nome: string;
  descricao: string;
  modelos: string[];
  prefixo?: string;
  pedeChave: boolean;
  pedeUrl?: boolean;
  pedeNome?: boolean;
  iconePlugin?: string;
}

export const PROVEDORES_MODELO: DefinicaoProvedor[] = [
  { id: 'openai', nome: 'OpenAI', descricao: 'GPT para conversa, raciocínio e multimodal.', modelos: ['gpt-5.5', 'gpt-5.5-mini', 'gpt-5.5-codex'], prefixo: 'sk-', pedeChave: true, iconePlugin: 'ChatGPT' },
  { id: 'anthropic', nome: 'Anthropic', descricao: 'Família Claude para escrita e raciocínio.', modelos: ['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5'], prefixo: 'sk-ant-', pedeChave: true, iconePlugin: 'Anthropic' },
  { id: 'gemini', nome: 'Google Gemini', descricao: 'Modelos multimodais do Google.', modelos: ['gemini-3.1-pro', 'gemini-3.8-flash'], prefixo: 'AIza', pedeChave: true, iconePlugin: 'Gemini' },
  { id: 'xai', nome: 'xAI (Grok)', descricao: 'Modelos Grok da xAI.', modelos: ['grok-4.7', 'grok-4.7-fast'], prefixo: 'xai-', pedeChave: true },
  { id: 'deepseek', nome: 'DeepSeek', descricao: 'Modelos de raciocínio e código.', modelos: ['deepseek-v4-pro', 'deepseek-v4'], prefixo: 'sk-', pedeChave: true },
  { id: 'mistral', nome: 'Mistral', descricao: 'Modelos abertos e comerciais da Mistral AI.', modelos: ['mistral-large-latest', 'codestral-latest'], pedeChave: true },
  { id: 'openrouter', nome: 'OpenRouter', descricao: 'Acesso unificado a modelos de vários provedores.', modelos: ['openrouter/auto', 'anthropic/claude-sonnet-5.5', 'google/gemini-3.1-pro'], prefixo: 'sk-or-', pedeChave: true },
  { id: 'ollama', nome: 'Ollama', descricao: 'Modelos executados localmente neste dispositivo.', modelos: ['llama3.3', 'qwen3', 'gemma3'], pedeChave: false, pedeUrl: true },
  { id: 'openai-compativel', nome: 'Compatível com OpenAI', descricao: 'Servidor próprio com API no formato OpenAI.', modelos: ['modelo-personalizado'], pedeChave: true, pedeUrl: true, pedeNome: true },
];

const CHAVE_STORAGE = 'sora.modelos.v1';
const porId = Object.fromEntries(PROVEDORES_MODELO.map(p => [p.id, p])) as Record<ProvedorModeloId, DefinicaoProvedor>;

function inicial(): EstadoModelos {
  const provedores = Object.fromEntries(PROVEDORES_MODELO.map(p => [p.id, {
    status: 'nao-conectado' as const,
    urlBase: p.id === 'ollama' ? 'http://localhost:11434' : '',
    modelos: p.modelos.map(id => ({ id, habilitado: true })),
  }])) as Record<ProvedorModeloId, ConfiguracaoProvedor>;
  return { versao: 1, provedores, padraoSora: null, padraoNovosAgentes: null, modelosPorAgente: {} };
}

function carregar(): EstadoModelos {
  try {
    const bruto = localStorage.getItem(CHAVE_STORAGE);
    if (!bruto) return inicial();
    const salvo = JSON.parse(bruto) as Partial<EstadoModelos>;
    if (salvo.versao !== 1 || !salvo.provedores) return inicial();
    const base = inicial();
    for (const p of PROVEDORES_MODELO) {
      const cfg = salvo.provedores[p.id];
      if (cfg) base.provedores[p.id] = { ...base.provedores[p.id], ...cfg, modelos: Array.isArray(cfg.modelos) ? cfg.modelos : base.provedores[p.id].modelos };
    }
    return { ...base, ...salvo, provedores: base.provedores, modelosPorAgente: salvo.modelosPorAgente ?? {} };
  } catch { return inicial(); }
}

let estado = typeof window === 'undefined' ? inicial() : carregar();
const ouvintes = new Set<() => void>();
const assinar = (fn: () => void) => { ouvintes.add(fn); return () => { ouvintes.delete(fn); }; };
export const lerModelos = () => estado;
export function useModelos() { return useSyncExternalStore(assinar, lerModelos, lerModelos); }

function definir(proximo: EstadoModelos) {
  estado = proximo;
  ouvintes.forEach(fn => fn());
  try { localStorage.setItem(CHAVE_STORAGE, JSON.stringify(estado)); } catch { /* segue somente em memória */ }
}

if (typeof window !== 'undefined') window.addEventListener('storage', ev => {
  if (ev.key === CHAVE_STORAGE) { estado = carregar(); ouvintes.forEach(fn => fn()); }
});

export function mascararChave(chave?: string) {
  if (!chave) return '';
  const inicio = chave.startsWith('sk-ant-') ? 'sk-ant-' : chave.slice(0, Math.min(3, chave.length));
  return `${inicio}…${chave.slice(-4)}`;
}

export interface ConfiguracaoTeste { chave?: string; urlBase?: string; nome?: string }

/** TODO(back-end): substituir apenas esta função por uma chamada segura ao servidor. */
export async function testarConexao(provedor: ProvedorModeloId, cfg: ConfiguracaoTeste): Promise<{ ok: boolean; mensagem: string }> {
  await new Promise(resolve => window.setTimeout(resolve, 950));
  const def = porId[provedor];
  const urlValida = !def.pedeUrl || /^https?:\/\/[\w.-]+(?::\d+)?(?:\/.*)?$/i.test(cfg.urlBase?.trim() ?? '');
  const chave = cfg.chave?.trim() ?? '';
  const chaveValida = !def.pedeChave || (def.prefixo ? chave.startsWith(def.prefixo) && chave.length >= def.prefixo.length + 8 : chave.length >= 12);
  const nomeValido = !def.pedeNome || (cfg.nome?.trim().length ?? 0) >= 2;
  if (!urlValida) return { ok: false, mensagem: 'Informe uma URL base válida, começando com http:// ou https://.' };
  if (!chaveValida) return { ok: false, mensagem: def.prefixo ? `A chave deve começar com ${def.prefixo}.` : 'A chave informada parece incompleta.' };
  if (!nomeValido) return { ok: false, mensagem: 'Dê um nome para esta conexão.' };
  return { ok: true, mensagem: 'Conexão simulada com sucesso.' };
}

export function salvarConfiguracao(provedor: ProvedorModeloId, patch: Partial<ConfiguracaoProvedor>) {
  definir({ ...estado, provedores: { ...estado.provedores, [provedor]: { ...estado.provedores[provedor], ...patch } } });
}
export function desconectarProvedor(provedor: ProvedorModeloId) {
  const cfg = estado.provedores[provedor];
  salvarConfiguracao(provedor, { ...cfg, chave: undefined, status: 'nao-conectado' });
}
export function definirModelosDoProvedor(provedor: ProvedorModeloId, modelos: ModeloConfigurado[]) { salvarConfiguracao(provedor, { modelos }); }
export function definirPadraoSora(escolha: EscolhaModelo | null) { definir({ ...estado, padraoSora: escolha }); }
export function definirPadraoNovosAgentes(escolha: EscolhaModelo | null) { definir({ ...estado, padraoNovosAgentes: escolha }); }
export function modeloDoAgente(id: string) { return estado.modelosPorAgente[id] ?? estado.padraoNovosAgentes; }
export function definirModeloAgente(id: string, provedor: ProvedorModeloId, modelo: string) {
  definir({ ...estado, modelosPorAgente: { ...estado.modelosPorAgente, [id]: { provedor, modelo } } });
}
export function apagarTodasAsChaves() {
  const provedores = { ...estado.provedores };
  for (const p of PROVEDORES_MODELO) provedores[p.id] = { ...provedores[p.id], chave: undefined, status: 'nao-conectado' };
  definir({ ...estado, provedores });
}

