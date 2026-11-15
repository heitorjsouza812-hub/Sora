import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import * as botsApi from '../../api/bots';
import * as gruposApi from '../../api/grupos';
import {
  _reiniciarCartoesSoraParaTestes, carregarPropostasPendentes, carregarRascunhosPendentes,
  marcarRascunhoDecididoAqui, receberEventoSora, useCartoesSora,
} from '../sora';

const rascunho = (id: string): botsApi.RascunhoBotSaida => ({ id, nome: 'Lume', funcao: 'Pesquisa', cor: '#56A8FF', instrucoes: '', ferramentas: [], rotina: null, status: 'rascunho' });
const proposta = (id: string) => ({ id, nome: 'Loja', motivo: 'Lance a loja', bots: [] });

describe('cartões da conversa da Sora', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => {
    _reiniciarCartoesSoraParaTestes();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('evento reentregue pelo SSE não cria cartão: só agenda a releitura do GET', async () => {
    const listar = vi.spyOn(gruposApi, 'listarPropostasGrupo').mockResolvedValue([]);
    const { result } = renderHook(() => useCartoesSora());
    act(() => {
      receberEventoSora({ tipo: 'grupo.proposto', dados: { id: 'velha-1', nome: 'Velha', pedido: '', bots_reaproveitados: [], bots_novos: [] } });
      receberEventoSora({ tipo: 'grupo.proposto', dados: { id: 'velha-2', nome: 'Velha', pedido: '', bots_reaproveitados: [], bots_novos: [] } });
    });
    expect(result.current.propostas).toHaveLength(0);
    await act(() => vi.advanceTimersByTimeAsync(450));
    expect(listar).toHaveBeenCalledTimes(1); // agrupada
    expect(result.current.propostas).toHaveLength(0);
  });

  it('proposta nova chega pela releitura e some na hora ao ser resolvida', async () => {
    vi.spyOn(gruposApi, 'listarPropostasGrupo').mockResolvedValue([proposta('p1')]);
    const { result } = renderHook(() => useCartoesSora());
    act(() => receberEventoSora({ tipo: 'grupo.proposto', dados: { id: 'p1' } }));
    await act(() => vi.advanceTimersByTimeAsync(450));
    expect(result.current.propostas.map(p => p.id)).toEqual(['p1']);
    act(() => receberEventoSora({ tipo: 'grupo.proposta.resolvida', dados: { proposta_id: 'p1', status: 'aceita' } }));
    expect(result.current.propostas).toHaveLength(0);
    // Leitura atrasada que ainda devolve p1 não traz o cartão de volta.
    await act(() => carregarPropostasPendentes());
    expect(result.current.propostas).toHaveLength(0);
  });

  it('rascunho decidido nesta tela fica com o resultado; o de outra aba some', async () => {
    vi.spyOn(botsApi, 'listarRascunhosBot').mockResolvedValue([rascunho('r1'), rascunho('r2')]);
    vi.spyOn(botsApi, 'listarBots').mockResolvedValue([]);
    const { result } = renderHook(() => useCartoesSora());
    await act(() => carregarRascunhosPendentes());
    expect(result.current.rascunhos.map(r => r.id)).toEqual(['r1', 'r2']);
    marcarRascunhoDecididoAqui('r1');
    act(() => {
      receberEventoSora({ tipo: 'bot.rascunho.resolvido', dados: { rascunho_id: 'r1', status: 'confirmado', agente_id: 'b1' } });
      receberEventoSora({ tipo: 'bot.rascunho.resolvido', dados: { rascunho_id: 'r2', status: 'descartado' } });
    });
    expect(result.current.rascunhos).toEqual([expect.objectContaining({ id: 'r1', resolucao: { status: 'confirmado', agenteId: 'b1' } })]);
    // Releitura com os dois ainda pendentes na resposta: r2 não volta e r1 mantém o resultado.
    await act(() => carregarRascunhosPendentes());
    expect(result.current.rascunhos).toEqual([expect.objectContaining({ id: 'r1', resolucao: { status: 'confirmado', agenteId: 'b1' } })]);
  });

  it('pedido de releitura durante uma leitura em voo roda depois dela', async () => {
    let soltar: (lista: ReturnType<typeof proposta>[]) => void = () => {};
    const listar = vi.spyOn(gruposApi, 'listarPropostasGrupo')
      .mockImplementationOnce(() => new Promise(resolve => { soltar = resolve; }))
      .mockResolvedValueOnce([proposta('p2')]);
    const { result } = renderHook(() => useCartoesSora());
    const primeira = carregarPropostasPendentes();
    act(() => receberEventoSora({ tipo: 'grupo.proposto', dados: { id: 'p2' } }));
    await act(() => vi.advanceTimersByTimeAsync(450));
    expect(listar).toHaveBeenCalledTimes(1);
    soltar([]);
    await act(async () => { await primeira; await vi.advanceTimersByTimeAsync(10); });
    expect(listar).toHaveBeenCalledTimes(2);
    expect(result.current.propostas.map(p => p.id)).toEqual(['p2']);
  });
});
