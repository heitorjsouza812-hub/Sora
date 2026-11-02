import { afterEach, describe, expect, it, vi } from 'vitest';

const buscarAutenticado = vi.hoisted(() => vi.fn());
vi.mock('../cliente', async (importar) => ({ ...(await importar<typeof import('../cliente')>()), buscarAutenticado }));

import { ErroApi } from '../cliente';
import { acompanharEventos } from '../eventos';

const fluxo = (texto: string) => new Response(new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode(texto)); c.close(); } }));

afterEach(() => { buscarAutenticado.mockReset(); });

describe('acompanharEventos', () => {
  it('se o Last-Event-ID for rejeitado com 400, recomeça de 0-0 uma vez e continua', async () => {
    buscarAutenticado
      .mockRejectedValueOnce(new ErroApi(400, 'Last-Event-ID inválido.'))
      .mockResolvedValueOnce(fluxo('id: 1730518324070-0\nevent: mensagem.fim\ndata: {"mensagem_id":"m"}\n\n'));
    const controlador = new AbortController();
    const recebidos: string[] = [];
    const erros: unknown[] = [];
    await new Promise<void>(resolver => {
      void acompanharEventos('/v1/conversas/x/eventos', {
        signal: controlador.signal, ultimoId: 'lixo',
        aoEvento: e => { recebidos.push(e.tipo); controlador.abort(); resolver(); },
        aoErro: e => erros.push(e),
      });
    });
    expect(buscarAutenticado.mock.calls[0]?.[1].headers['Last-Event-ID']).toBe('lixo');
    expect(buscarAutenticado.mock.calls[1]?.[1].headers['Last-Event-ID']).toBe('0-0');
    expect(recebidos).toEqual(['mensagem.fim']);
    expect(erros).toEqual([]);
  });
});
