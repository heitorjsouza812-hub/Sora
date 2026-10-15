import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { abrirIlha, fecharIlha, useIlhaUi } from '../ilhaUi';

describe('ilhaUi', () => {
  it('não transforma a abertura por hover em pedido externo fixado', () => {
    const { result } = renderHook(() => useIlhaUi());
    const pedidoInicial = result.current.pedido;

    act(() => abrirIlha('inicio', undefined, { porHover: true }));

    expect(result.current).toMatchObject({ aberta: true, pedido: pedidoInicial });

    act(() => fecharIlha());
    act(() => abrirIlha());

    expect(result.current).toMatchObject({ aberta: true, pedido: pedidoInicial + 1 });
  });
});
