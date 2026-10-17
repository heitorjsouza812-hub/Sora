// Cliente HTTP do app com o backend da Sora (etapa 2, regras 1 e 2 de log/etapa2-app-provedores.md).
//
// • Base: import.meta.env.VITE_API_URL (padrão '' = mesma origem; no dev o Vite faz proxy de /v1).
// • Token de acesso SÓ em memória (nunca localStorage).
// • 401 → uma única renovação em voo (POST /v1/auth/renovar) e o pedido é repetido uma vez;
//   se a renovação falhar, a sessão é encerrada e quem ouve aoSessaoEncerrada mostra a tela Entrar.
// • Web: token de renovação no cookie httpOnly (credentials: 'include').
//   Desktop (Tauri): cabeçalho X-Sora-Cliente: desktop; o token de renovação vem no corpo e fica no
//   cofre do sistema (cofreLer/cofreGravar/cofreApagar em desktop/ponte.ts).
// • Erros viram ErroApi { status, mensagem } com a mensagem PT-BR do backend (`detail`).
import { cofreApagar, cofreGravar, cofreLer, noDesktop } from '../desktop/ponte';

export const API_BASE: string = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/+$/, '') ?? '';

export const MSG_SEM_REDE = 'Não foi possível falar com o servidor da Sora.';
const MSG_GENERICA = 'Algo deu errado no servidor da Sora. Tente de novo.';
const MSG_VALIDACAO = 'Confira os campos e tente de novo.';
const MSG_LIMITE = 'Muitas tentativas. Espere um pouco e tente de novo.';

/** Erro de qualquer chamada à API. `status` 0 = sem rede. */
export class ErroApi extends Error {
  readonly status: number;
  readonly mensagem: string;
  /** Segundos do cabeçalho Retry-After (429). */
  readonly tentarEmSegundos?: number;
  /** Corpo `detail` cru (ex.: lista de erros de validação do 422). */
  readonly detalhe?: unknown;

  constructor(status: number, mensagem: string, extra: { tentarEmSegundos?: number; detalhe?: unknown } = {}) {
    super(mensagem);
    this.name = 'ErroApi';
    this.status = status;
    this.mensagem = mensagem;
    this.tentarEmSegundos = extra.tentarEmSegundos;
    this.detalhe = extra.detalhe;
  }
}

export const ehErroApi = (e: unknown): e is ErroApi => e instanceof ErroApi;

/** Mensagem pronta para mostrar ao usuário a partir de qualquer erro. */
export function mensagemDeErro(e: unknown): string {
  return ehErroApi(e) ? e.mensagem : MSG_GENERICA;
}

export interface OpcoesPedido {
  signal?: AbortSignal;
  /** Não manda o token nem tenta renovar (rotas públicas: entrar, cadastrar). */
  semAuth?: boolean;
}

export interface TokensSaida { token_acesso: string; token_renovacao?: string | null }

// ── Token de acesso (memória) e aviso de sessão encerrada ────────────────────────────────

let tokenAcesso: string | null = null;
const ouvintesEncerrada = new Set<() => void>();

export function definirTokenAcesso(token: string | null): void { tokenAcesso = token; }
export function temTokenAcesso(): boolean { return tokenAcesso !== null; }

/** Chamado quando a renovação falha (sessão perdida). Devolve a função para parar de ouvir. */
export function aoSessaoEncerrada(cb: () => void): () => void {
  ouvintesEncerrada.add(cb);
  return () => { ouvintesEncerrada.delete(cb); };
}

function encerrarSessaoLocal(): void {
  tokenAcesso = null;
  for (const cb of [...ouvintesEncerrada]) cb();
}

// ── Montagem do pedido ───────────────────────────────────────────────────────────────────

function cabecalhosBase(): Record<string, string> {
  const h: Record<string, string> = { Accept: 'application/json' };
  if (noDesktop) h['X-Sora-Cliente'] = 'desktop';
  return h;
}

function mensagemDoDetalhe(status: number, detalhe: unknown): string {
  if (typeof detalhe === 'string' && detalhe.trim()) return detalhe;
  if (status === 422) return MSG_VALIDACAO;
  if (status === 429) return MSG_LIMITE;
  return MSG_GENERICA;
}

async function lerCorpo(resp: Response): Promise<unknown> {
  if (resp.status === 204) return undefined;
  const texto = await resp.text();
  if (!texto) return undefined;
  try { return JSON.parse(texto); } catch { return texto; }
}

async function erroDaResposta(resp: Response): Promise<ErroApi> {
  const corpo = await lerCorpo(resp).catch(() => undefined);
  const detalhe = corpo && typeof corpo === 'object' && 'detail' in corpo ? (corpo as { detail: unknown }).detail : undefined;
  const retry = resp.headers.get('Retry-After');
  const tentarEmSegundos = retry !== null && /^\d+$/.test(retry.trim()) ? Number(retry) : undefined;
  return new ErroApi(resp.status, mensagemDoDetalhe(resp.status, detalhe), { tentarEmSegundos, detalhe });
}

async function buscar(caminho: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(`${API_BASE}${caminho}`, init);
  } catch (e) {
    if ((e as { name?: string })?.name === 'AbortError') throw e;
    throw new ErroApi(0, MSG_SEM_REDE);
  }
}

// ── Renovação (uma só em voo) ────────────────────────────────────────────────────────────

let renovacaoEmVoo: Promise<boolean> | null = null;

async function fazerRenovacao(): Promise<boolean> {
  let corpo: string | undefined;
  if (noDesktop) {
    const salvo = await cofreLer().catch(() => null);
    if (!salvo) return false;
    corpo = JSON.stringify({ token_renovacao: salvo });
  }
  const headers = cabecalhosBase();
  if (corpo) headers['Content-Type'] = 'application/json';
  let resp: Response;
  try {
    resp = await buscar('/v1/auth/renovar', { method: 'POST', headers, body: corpo, credentials: 'include' });
  } catch (e) {
    // Sem rede: não derruba a sessão do cofre; só não renovou agora.
    if (ehErroApi(e) && e.status === 0) throw e;
    return false;
  }
  if (!resp.ok) {
    if (resp.status === 401 || resp.status === 403) {
      if (noDesktop) await cofreApagar().catch(() => {});
      return false;
    }
    throw await erroDaResposta(resp);
  }
  await guardarTokens((await lerCorpo(resp)) as TokensSaida);
  return true;
}

/** Guarda os tokens recebidos de entrar/renovar (acesso em memória; renovação no cofre, se desktop). */
export async function guardarTokens(t: TokensSaida): Promise<void> {
  tokenAcesso = t.token_acesso;
  if (noDesktop && t.token_renovacao) await cofreGravar(t.token_renovacao);
}

/** Tenta renovar a sessão (abertura do app ou 401). Várias chamadas juntas dividem o mesmo pedido.
 *  true = há token de acesso novo; false = sem sessão. Lança ErroApi(0) se o servidor estiver fora. */
export function renovarSessao(): Promise<boolean> {
  if (!renovacaoEmVoo) {
    renovacaoEmVoo = fazerRenovacao().finally(() => { renovacaoEmVoo = null; });
  }
  return renovacaoEmVoo;
}

/** Esquece a sessão localmente (token em memória e cofre do desktop). Não avisa os ouvintes. */
export async function limparSessaoLocal(): Promise<void> {
  tokenAcesso = null;
  if (noDesktop) await cofreApagar().catch(() => {});
}

/** Corpo para rotas que aceitam o token de renovação no corpo (desktop): /auth/sair. */
export async function corpoRenovacaoDesktop(): Promise<{ token_renovacao: string } | undefined> {
  if (!noDesktop) return undefined;
  const t = await cofreLer().catch(() => null);
  return t ? { token_renovacao: t } : undefined;
}

// ── Pedido genérico ──────────────────────────────────────────────────────────────────────

type Metodo = 'GET' | 'POST' | 'PATCH' | 'DELETE';

async function pedir<T>(metodo: Metodo, caminho: string, corpo: unknown, opcoes: OpcoesPedido = {}): Promise<T> {
  const montar = (): RequestInit => {
    const headers = cabecalhosBase();
    if (corpo !== undefined) headers['Content-Type'] = 'application/json';
    if (!opcoes.semAuth && tokenAcesso) headers.Authorization = `Bearer ${tokenAcesso}`;
    return {
      method: metodo,
      headers,
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
      signal: opcoes.signal,
      // O cookie de renovação só vale em /v1/auth; incluir em tudo permite API em outra origem.
      credentials: 'include',
    };
  };

  let resp = await buscar(caminho, montar());
  if (resp.status === 401 && !opcoes.semAuth) {
    let renovou: boolean;
    try {
      renovou = await renovarSessao();
    } catch (erro) {
      // O acesso já foi recusado e a renovação também falhou (inclusive por rede/5xx):
      // não deixe um token expirado aparentar uma sessão válida no restante do app.
      encerrarSessaoLocal();
      throw erro;
    }
    if (!renovou) {
      encerrarSessaoLocal();
      throw await erroDaResposta(resp);
    }
    resp = await buscar(caminho, montar());
    if (resp.status === 401) {
      encerrarSessaoLocal();
      throw await erroDaResposta(resp);
    }
  }
  if (!resp.ok) throw await erroDaResposta(resp);
  return (await lerCorpo(resp)) as T;
}

/** Caminhos sempre começam com "/v1/…". 204 devolve undefined. */
export const api = {
  get: <T>(caminho: string, opcoes?: OpcoesPedido) => pedir<T>('GET', caminho, undefined, opcoes),
  post: <T>(caminho: string, corpo?: unknown, opcoes?: OpcoesPedido) => pedir<T>('POST', caminho, corpo, opcoes),
  patch: <T>(caminho: string, corpo?: unknown, opcoes?: OpcoesPedido) => pedir<T>('PATCH', caminho, corpo, opcoes),
  delete: <T>(caminho: string, corpo?: unknown, opcoes?: OpcoesPedido) => pedir<T>('DELETE', caminho, corpo, opcoes),
};

/** Só para testes: zera o estado em memória. */
export function _reiniciarClienteParaTestes(): void {
  tokenAcesso = null;
  renovacaoEmVoo = null;
}
