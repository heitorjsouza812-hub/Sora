import { describe, expect, it, vi } from 'vitest';
import { navegarAtePedido } from './focarPedido';

describe('navegarAtePedido', () => {
  it('navega e leva o foco ao cartão do pedido', async () => {
    const cartao = document.createElement('section');
    cartao.dataset.pedidoId = 'apr:42';
    cartao.tabIndex = -1;
    cartao.scrollIntoView = vi.fn();
    document.body.appendChild(cartao);
    const navigate = vi.fn();
    navegarAtePedido(navigate, `/bots/b1#pedido-${encodeURIComponent('apr:42')}`);
    expect(navigate).toHaveBeenCalledWith('/bots/b1#pedido-apr%3A42');
    expect(cartao.scrollIntoView).toHaveBeenCalled();
    expect(document.activeElement).toBe(cartao);
    cartao.remove();
  });

  it('caminho sem pedido só navega', () => {
    const navigate = vi.fn();
    navegarAtePedido(navigate, '/grupos/g1');
    expect(navigate).toHaveBeenCalledWith('/grupos/g1');
  });
});
