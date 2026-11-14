// Depois de navegar para "/bots/x#pedido-ID", leva a tela até o cartão daquele pedido.
const PREFIXO = '#pedido-';

export function navegarAtePedido(navigate: (caminho: string) => void, caminho: string): void {
  navigate(caminho);
  const i = caminho.indexOf(PREFIXO);
  if (i >= 0) focarPedido(decodeURIComponent(caminho.slice(i + PREFIXO.length)));
}

export function focarPedido(id: string, prazoMs = 3000): void {
  const inicio = Date.now();
  const tentar = () => {
    const seletor = `[data-pedido-id="${typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(id) : id.replace(/"/g, '\\"')}"]`;
    const alvo = document.querySelector<HTMLElement>(seletor);
    if (alvo) {
      alvo.scrollIntoView({ block: 'center', behavior: 'smooth' });
      alvo.focus({ preventScroll: true });
      return;
    }
    if (Date.now() - inicio < prazoMs) window.setTimeout(tentar, 100);
  };
  tentar();
}
