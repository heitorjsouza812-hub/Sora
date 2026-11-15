// Pedido que outra tela deixa pronto para a Sora: a tela de conversa lê e preenche o campo
// (sem enviar). Vive fora do React para sobreviver à troca de rota.
let pendente: string | null = null;
const ouvintes = new Set<() => void>();

/** Deixa um texto para o campo da Sora; quem abre `/` o consome ao montar (ou, se a tela já está aberta, ao ser avisada). */
export function deixarPedidoInicial(texto: string) { pendente = texto; ouvintes.forEach(f => f()); }

/** Avisa quando um pedido novo é deixado (a tela da Sora já aberta o consome na hora). Devolve a função que cancela. */
export function aoDeixarPedidoInicial(f: () => void): () => void { ouvintes.add(f); return () => { ouvintes.delete(f); }; }

/** Lê e limpa o texto deixado (ou `null`). */
export function consumirPedidoInicial(): string | null {
  const t = pendente; pendente = null; return t;
}

/** Começos de pedido da tela vazia: só preenchem o campo. */
export const INICIOS_DE_PEDIDO = [
  "Quero um bot que todo dia de manhã me traga as notícias de ",
  "Crie um bot para pesquisar e resumir ",
  "Monte um grupo para planejar ",
  "Preciso de um bot que me ajude a escrever ",
] as const;
