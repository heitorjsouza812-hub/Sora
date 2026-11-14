// Ponte com o app de desktop (Tauri). CONTRATO — não renomear exports.
// No navegador tudo aqui vira "não faz nada" (noDesktop = false), então o app web segue igual.
//
// Janelas do app de desktop (src-tauri/tauri.conf.json):
//   • "main" → o app da Sora inteiro (index.html)
//   • "ilha" → só a Ilha da Sora, janela transparente, sem borda, sempre no topo, presa no alto da tela
//              (index.html?janela=ilha). Tamanho fixo ILHA_JANELA; fora do retângulo informado em
//              informarRetanguloIlha os cliques atravessam para o que estiver embaixo.
//
import { invoke } from '@tauri-apps/api/core';
import { emit, listen, type UnlistenFn } from '@tauri-apps/api/event';

export type Janela = 'web' | 'main' | 'ilha';

/** true quando roda dentro do app de desktop (Tauri). */
export const noDesktop: boolean = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;

/** Qual janela é esta. */
export const janelaAtual: Janela = !noDesktop
  ? 'web'
  : new URLSearchParams(window.location.search).get('janela') === 'ilha' ? 'ilha' : 'main';

/** Tamanho lógico (px) da janela transparente da ilha; a pílula fica centralizada no topo dela. */
export const ILHA_JANELA = { largura: 800, altura: 460 } as const;

export interface Retangulo { x: number; y: number; w: number; h: number }
export interface MouseIlha { dentro: boolean; x: number; y: number }

function ouvir<T>(evento: string, cb: (payload: T) => void): () => void {
  if (!noDesktop) return () => {};
  let ativo = true;
  let remover: UnlistenFn | null = null;
  void listen<T>(evento, ({ payload }) => cb(payload)).then((unlisten) => {
    if (ativo) remover = unlisten;
    else unlisten();
  });
  return () => {
    ativo = false;
    remover?.();
  };
}

/** A janela da ilha informa onde a pílula/painel está desenhado (px lógicos, relativos à janela).
 *  Fora desse retângulo (+ margem) o Rust deixa os cliques atravessarem. */
export async function informarRetanguloIlha(r: Retangulo): Promise<void> {
  if (noDesktop) await invoke('ilha_retangulo', { x: r.x, y: r.y, w: r.w, h: r.h });
}

/** Posição do cursor relativa à janela da ilha (o Rust envia ~30×/s enquanto a ilha está visível).
 *  Serve para o hover/mouse saindo e para a Sora olhar para o mouse mesmo com os cliques atravessando. */
export function aoMouseIlha(cb: (m: MouseIlha) => void): () => void {
  return ouvir<MouseIlha>('ilha-mouse', cb);
}

/** Só rotas internas do app (ex. "/revisao/abc"): uma única "/" no início, sem esquema, "//", barra invertida ou "..". */
export function caminhoInternoValido(caminho: unknown): caminho is string {
  return typeof caminho === 'string' && caminho.length <= 200 && /^\/(?!\/)[\w\-./?=&%#]*$/.test(caminho) && !caminho.includes('..');
}

/** Só chaves do próprio app atravessam a ponte de armazenamento entre janelas. */
export const chaveDaSora = (chave: unknown): chave is string => typeof chave === 'string' && /^sora\.[\w.-]{1,80}$/.test(chave);

/** Da janela da ilha: abre um caminho do app (ex. "/revisao/abc") na janela principal e a traz para frente. */
export async function abrirNoApp(caminho: string): Promise<void> {
  if (noDesktop && caminhoInternoValido(caminho)) await invoke('navegar', { caminho });
}

/** Na janela principal: recebe os pedidos de navegação vindos da ilha. */
export function aoNavegar(cb: (caminho: string) => void): () => void {
  return ouvir<string>('sora-navegar', caminho => { if (caminhoInternoValido(caminho)) cb(caminho); });
}

/** Mostra/esconde a janela da ilha (ex. preferência "Mostrar ilha"). */
export async function definirIlhaVisivel(visivel: boolean): Promise<void> {
  if (noDesktop) await invoke('ilha_visivel', { visivel });
}

/** Na janela da ilha: atalho global Ctrl+Shift+S ou item da bandeja pediram para abrir/fechar a ilha. */
export function aoAlternarIlha(cb: () => void): () => void {
  return ouvir<null>('ilha-alternar', cb);
}

/** Na janela da ilha: o Rust escondeu a janela (o usuário voltou à Sora). Etapa 5. */
export function aoEsconderIlha(cb: () => void): () => void {
  return ouvir<null>('ilha-escondida', cb);
}

/** Traz a janela principal para frente. */
export async function mostrarApp(): Promise<void> {
  if (noDesktop) await invoke('mostrar_app');
}

/** Lê o token de renovação do cofre do sistema. Web e Ilha não acessam o cofre. */
export async function cofreLer(): Promise<string | null> {
  if (!noDesktop || janelaAtual !== 'main') return null;
  return invoke<string | null>('cofre_ler');
}

/** Guarda o token de renovação exatamente como recebido do backend. */
export async function cofreGravar(token: string): Promise<void> {
  if (!noDesktop || janelaAtual !== 'main') return;
  await invoke('cofre_gravar', { token });
}

/** Remove o token de renovação; apagar uma entrada inexistente também é sucesso. */
export async function cofreApagar(): Promise<void> {
  if (!noDesktop || janelaAtual !== 'main') return;
  await invoke('cofre_apagar');
}

// WebView2 nem sempre propaga `storage` entre duas WebViews do mesmo app. Reemitimos cada
// mutação via eventos Tauri; os stores continuam usando o evento web e não conhecem esta ponte.
interface ArmazenamentoTauri { chave: string; origem: string }
type JanelaComPonte = Window & { __SORA_ARMAZENAMENTO_PONTE__?: boolean };

function instalarPonteArmazenamento() {
  if (!noDesktop || typeof window === 'undefined') return;
  const janela = window as JanelaComPonte;
  if (janela.__SORA_ARMAZENAMENTO_PONTE__) return;
  janela.__SORA_ARMAZENAMENTO_PONTE__ = true;
  const origem = crypto.randomUUID();
  const originalSet = Storage.prototype.setItem;
  const originalRemove = Storage.prototype.removeItem;
  const originalClear = Storage.prototype.clear;
  const anunciar = (chave: string) => { void emit<ArmazenamentoTauri>('sora-armazenamento', { chave, origem }); };

  Storage.prototype.setItem = function setItem(chave, valor) {
    originalSet.call(this, chave, valor);
    if (this === window.localStorage) anunciar(chave);
  };
  Storage.prototype.removeItem = function removeItem(chave) {
    originalRemove.call(this, chave);
    if (this === window.localStorage) anunciar(chave);
  };
  Storage.prototype.clear = function clear() {
    const chaves = this === window.localStorage ? Array.from({ length: this.length }, (_, i) => this.key(i)).filter((x): x is string => !!x) : [];
    originalClear.call(this);
    chaves.forEach(anunciar);
  };

  void listen<ArmazenamentoTauri>('sora-armazenamento', ({ payload }) => {
    if (payload?.origem === origem || !chaveDaSora(payload?.chave)) return;
    const valor = localStorage.getItem(payload.chave);
    window.dispatchEvent(new StorageEvent('storage', {
      key: payload.chave,
      newValue: valor,
      storageArea: localStorage,
      url: window.location.href,
    }));
  });
}

instalarPonteArmazenamento();

// ── Sessão compartilhada com a janela da ilha ────────────────────────────────────────────────
// Só a janela principal enxerga o cofre do sistema (token de renovação). A ilha nunca renova por
// conta própria (renovar em duas janelas gastaria o mesmo token de renovação e a detecção de
// reuso derrubaria a sessão): ela PEDE o token de acesso (curto, só em memória) à principal, que
// renova quando precisa e avisa a ilha pelos eventos abaixo.
export interface PedidoSessao { id: string; tokenAtual: string | null }
export interface RespostaSessao { id?: string; token: string | null }

/** Na principal: a ilha pediu o token de acesso (`tokenAtual` = o que ela já tem e não serviu). */
export function aoPedirSessao(cb: (p: PedidoSessao) => void): () => void {
  return ouvir<PedidoSessao>('sora-sessao-pedir', cb);
}

/** Na principal: entrega (ou avisa que não há) o token de acesso. `id` responde a um pedido; sem
 *  `id` é aviso espontâneo (login, renovação ou saída na principal). */
export async function emitirSessao(token: string | null, id?: string): Promise<void> {
  if (noDesktop && janelaAtual === 'main') await emit<RespostaSessao>('sora-sessao', { id, token });
}

/** Na ilha: avisos espontâneos da principal (sem `id`). */
export function aoMudarSessaoNoPrincipal(cb: (token: string | null) => void): () => void {
  return ouvir<RespostaSessao>('sora-sessao', r => { if (!r?.id) cb(typeof r?.token === 'string' ? r.token : null); });
}

/** Na ilha: pede o token de acesso à principal. null = principal sem sessão (ou sem resposta). */
export async function pedirSessaoAoPrincipal(tokenAtual: string | null, esperaMs = 15000): Promise<string | null> {
  if (!noDesktop || janelaAtual !== 'ilha') return null;
  const id = crypto.randomUUID();
  let resolver: (token: string | null) => void = () => {};
  const resposta = new Promise<string | null>(r => { resolver = r; });
  // o ouvinte precisa estar pronto ANTES de pedir, senão uma resposta rápida se perde
  const parar = await listen<RespostaSessao>('sora-sessao', ({ payload }) => {
    if (payload?.id === id) resolver(typeof payload.token === 'string' ? payload.token : null);
  });
  const tempo = window.setTimeout(() => resolver(null), esperaMs);
  try {
    await emit<PedidoSessao>('sora-sessao-pedir', { id, tokenAtual });
    return await resposta;
  } catch {
    return null;
  } finally {
    window.clearTimeout(tempo);
    parar();
  }
}
