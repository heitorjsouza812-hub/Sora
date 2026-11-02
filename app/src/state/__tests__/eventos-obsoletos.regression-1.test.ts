import { afterEach, describe, expect, it, vi } from 'vitest';

const get = vi.hoisted(() => vi.fn());
vi.mock('../../api/cliente', async (importar) => ({
  ...(await importar<typeof import('../../api/cliente')>()),
  api: { get, post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import {
  _aplicarEventoParaTestes,
  _reiniciarProjetosParaTestes,
  lerEstado,
} from '../projetos';

afterEach(() => { get.mockReset(); _reiniciarProjetosParaTestes(); });

describe('eventos obsoletos do canal agregado', () => {
  // Regression: ISSUE-004 — eventos retidos de conversas apagadas recriavam agentes e faziam GETs 404
  // Found by /qa on 2026-11-02
  // Report: .gstack/qa-reports/qa-report-sora-local-2026-11-02.md
  it('ignora eventos cuja conversa não existe mais na hidratação atual', () => {
    _aplicarEventoParaTestes({
      id: '1-0', tipo: 'agente.criado', recebidoEm: 1,
      dados: { conversa_id: 'apagada', agente_id: 'fantasma', nome: 'Fantasma', funcao: 'Teste', cor: '#56A8FF', movimento: 'gira' },
    });
    _aplicarEventoParaTestes({
      id: '2-0', tipo: 'entrega', recebidoEm: 2,
      dados: { conversa_id: 'apagada', entrega_id: 'e1', agente_id: 'fantasma', versao: 1, tipo: 'texto', titulo: 'Antiga', resumo: 'Antiga' },
    });

    expect(lerEstado().agentes).toEqual({});
    expect(get).not.toHaveBeenCalled();
  });
});
