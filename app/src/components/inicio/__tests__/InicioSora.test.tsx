import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { consumirPedidoInicial, deixarPedidoInicial, InicioSora, INICIOS_DE_PEDIDO } from '..';

vi.mock('../../../state/sessao', () => ({ useSessao: () => ({ usuario: { tem_provedor: false } }) }));

describe('InicioSora', () => {
  it('avisa da chave e só preenche o campo ao clicar num começo de pedido', () => {
    const preencher = vi.fn();
    render(<MemoryRouter><InicioSora onPreencher={preencher} /></MemoryRouter>);
    expect(screen.getByRole('status')).toHaveTextContent('Nenhuma API de IA conectada');
    expect(screen.getAllByRole('button')).toHaveLength(INICIOS_DE_PEDIDO.length);
    fireEvent.click(screen.getAllByRole('button')[1]);
    expect(preencher).toHaveBeenCalledWith(INICIOS_DE_PEDIDO[1]);
  });

  it('entrega o pedido deixado por outra tela uma única vez', () => {
    deixarPedidoInicial('Quero um bot que ');
    expect(consumirPedidoInicial()).toBe('Quero um bot que ');
    expect(consumirPedidoInicial()).toBeNull();
  });
});
