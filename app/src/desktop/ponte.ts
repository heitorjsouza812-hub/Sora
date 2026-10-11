// Ponte com o app de desktop (Tauri). CONTRATO — não renomear exports.
// No navegador tudo aqui vira "não faz nada" (noDesktop = false), então o app web segue igual.
//
// Janelas do app de desktop (src-tauri/tauri.conf.json):
//   • "main" → o app da Sora inteiro (index.html)
//   • "ilha" → só a Ilha da Sora, janela transparente, sem borda, sempre no topo, presa no alto da tela
//              (index.html?janela=ilha). Tamanho fixo ILHA_JANELA; fora do retângulo informado em
//              informarRetanguloIlha os cliques atravessam para o que estiver embaixo.
//
// STUB do orquestrador: o Tear implementa com @tauri-apps/api mantendo estas assinaturas.

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

/** A janela da ilha informa onde a pílula/painel está desenhado (px lógicos, relativos à janela).
 *  Fora desse retângulo (+ margem) o Rust deixa os cliques atravessarem. */
export async function informarRetanguloIlha(_r: Retangulo): Promise<void> {}

/** Posição do cursor relativa à janela da ilha (o Rust envia ~30×/s enquanto a ilha está visível).
 *  Serve para o hover/mouse saindo e para a Sora olhar para o mouse mesmo com os cliques atravessando. */
export function aoMouseIlha(_cb: (m: MouseIlha) => void): () => void { return () => {}; }

/** Da janela da ilha: abre um caminho do app (ex. "/revisao/abc") na janela principal e a traz para frente. */
export async function abrirNoApp(_caminho: string): Promise<void> {}

/** Na janela principal: recebe os pedidos de navegação vindos da ilha. */
export function aoNavegar(_cb: (caminho: string) => void): () => void { return () => {}; }

/** Mostra/esconde a janela da ilha (ex. preferência "Mostrar ilha"). */
export async function definirIlhaVisivel(_visivel: boolean): Promise<void> {}

/** Na janela da ilha: atalho global Ctrl+Shift+S ou item da bandeja pediram para abrir/fechar a ilha. */
export function aoAlternarIlha(_cb: () => void): () => void { return () => {}; }

/** Traz a janela principal para frente. */
export async function mostrarApp(): Promise<void> {}
