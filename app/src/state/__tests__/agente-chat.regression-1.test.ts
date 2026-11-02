import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const get = vi.hoisted(() => vi.fn());
const post = vi.hoisted(() => vi.fn());
const acompanharEventos = vi.hoisted(() => vi.fn(() => new Promise<void>(() => {})));

vi.mock('../../api/cliente', async (importar) => ({
  ...(await importar<typeof import('../../api/cliente')>()),
  api: { get, post, patch: vi.fn(), delete: vi.fn() },
}));
vi.mock('../../api/eventos', async (importar) => ({
  ...(await importar<typeof import('../../api/eventos')>()),
  acompanharEventos,
}));

import {
  _definirEstadoParaTestes,
  _reiniciarProjetosParaTestes,
  capturarSnapshot,
  enviarParaAgente,
  lerEstado,
} from '../projetos';

const agora = '2026-11-02T12:00:00Z';

beforeEach(() => {
  get.mockReset(); post.mockReset(); acompanharEventos.mockClear();
  _definirEstadoParaTestes({
    ...capturarSnapshot(),
    agentes: {
      agente1: {
        id: 'agente1', projetoId: '', nome: 'Lume', funcao: 'Redatora', cor: '#56A8FF', tipoMovimento: 'gira',
        ferramentas: [], status: 'aguardando', verbo: 'Escrevendo', espera: 'Aguardando', instrucoes: '', avulso: true, criadoEm: 1,
      },
    },
  });
});

afterEach(() => _reiniciarProjetosParaTestes());

describe('chat de agente individual', () => {
  // Regression: ISSUE-003 — o primeiro envio para agente configurado era descartado sem criar conversa
  // Found by /qa on 2026-11-02
  // Report: .gstack/qa-reports/qa-report-sora-local-2026-11-02.md
  it('cria uma conversa real no primeiro envio e serializa o envio seguinte nela', async () => {
    post.mockImplementation((caminho: string) => {
      if (caminho === '/v1/conversas') return Promise.resolve({ id: 'conversa1', agente_id: 'agente1', tipo: 'agente', titulo: 'Primeira', aprovada_versao: null, criada_em: agora, atualizada_em: agora });
      if (caminho === '/v1/conversas/conversa1/mensagens') return Promise.resolve({ mensagem_id: 'm2' });
      throw new Error(`POST inesperado: ${caminho}`);
    });
    get.mockResolvedValue([{ id: 'm1', conversa_id: 'conversa1', autor: 'usuario', agente_id: null, conteudo: 'Primeira', anexos: [], criada_em: agora }]);

    await Promise.all([
      enviarParaAgente('agente1', 'Primeira'),
      enviarParaAgente('agente1', 'Segunda'),
    ]);

    expect(post.mock.calls.map(([caminho]) => caminho)).toEqual(['/v1/conversas', '/v1/conversas/conversa1/mensagens']);
    expect(lerEstado().agentes.agente1?.conversaId).toBe('conversa1');
    expect(lerEstado().mensagens.map(m => m.texto)).toEqual(['Primeira', 'Segunda']);
    expect(acompanharEventos).toHaveBeenCalledTimes(1);
  });
});
