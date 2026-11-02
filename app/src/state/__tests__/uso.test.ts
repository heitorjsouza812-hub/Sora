import { afterEach, describe, expect, it, vi } from 'vitest';

const get = vi.hoisted(() => vi.fn());
vi.mock('../../api/cliente', async (importar) => ({
  ...(await importar<typeof import('../../api/cliente')>()),
  api: { get },
}));

import { _reiniciarUsoParaTestes, carregarUso, lerUso, totalTokens } from '../uso';

afterEach(() => { get.mockReset(); _reiniciarUsoParaTestes(); });

describe('uso real do backend', () => {
  it('carrega custo e tokens de /v1/uso sem persistência local', async () => {
    localStorage.clear();
    get.mockResolvedValue({
      custo_total_usd: 1.25,
      itens: [{
        data: '2026-11-02T00:00:00Z', papel: 'especialista', provedor: 'openai',
        tokens_entrada: 100, tokens_saida: 50, custo_usd: 1.25,
      }],
    });
    await carregarUso();
    expect(get).toHaveBeenCalledWith('/v1/uso');
    expect(lerUso().custoTotalUsd).toBe(1.25);
    expect(totalTokens(lerUso())).toBe(150);
    expect(Object.keys(localStorage)).toEqual([]);
  });
});
