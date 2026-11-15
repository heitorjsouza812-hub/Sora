import { beforeEach, describe, expect, it, vi } from 'vitest';

const listar = vi.hoisted(() => vi.fn());
vi.mock('../../api/grupos', async (importar) => {
  const original = await importar<typeof import('../../api/grupos')>();
  return { ...original, listarPedidosAtencao: listar };
});

import { _reiniciarAtencaoParaTestes, carregarPrecisaDeVoce, lerPrecisaDeVoce, receberEventoAtencao } from '../atencao';

const pedido = (id: string) => ({ id, tipo: 'aprovacao' as const, titulo: 'Aprovar ação', resumo: 'Ravi quer mudar as próprias instruções.', botId: 'b1' });

describe('releitura de Precisa de você', () => {
  beforeEach(() => { listar.mockReset(); _reiniciarAtencaoParaTestes(); });

  it('releitura pedida durante uma leitura em voo não se perde', async () => {
    let soltar: (valor: unknown) => void = () => undefined;
    listar.mockImplementationOnce(() => new Promise(resolve => { soltar = resolve; }));
    listar.mockResolvedValueOnce([pedido('p1')]);
    const primeira = carregarPrecisaDeVoce(true);
    await carregarPrecisaDeVoce(true); // chega o evento enquanto a 1ª leitura (velha) está em voo
    soltar([]);
    await primeira;
    await vi.waitFor(() => expect(lerPrecisaDeVoce().porBot.b1).toBe(1));
    expect(listar).toHaveBeenCalledTimes(2);
  });

  it('evento de atenção relê GET /v1/atencao (agrupado)', async () => {
    vi.useFakeTimers();
    try {
      listar.mockResolvedValue([pedido('p9')]);
      receberEventoAtencao({ tipo: 'precisa_de_voce.atualizado' });
      receberEventoAtencao({ tipo: 'aprovacao.pedida' });
      receberEventoAtencao({ tipo: 'canal.mensagem' });
      await vi.advanceTimersByTimeAsync(500);
      expect(listar).toHaveBeenCalledTimes(1);
      expect(lerPrecisaDeVoce().porBot.b1).toBe(1);
    } finally { vi.useRealTimers(); }
  });

  it('sem releitura pendente, lê uma vez só', async () => {
    listar.mockResolvedValue([]);
    await carregarPrecisaDeVoce();
    await carregarPrecisaDeVoce();
    expect(listar).toHaveBeenCalledTimes(1);
  });
});
