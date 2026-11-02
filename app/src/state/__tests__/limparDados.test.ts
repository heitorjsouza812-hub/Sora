import { afterEach, describe, expect, it, vi } from 'vitest';

const excluir = vi.hoisted(() => vi.fn(async (_caminho: string) => undefined));
vi.mock('../../api/cliente', async (importar) => ({
  ...(await importar<typeof import('../../api/cliente')>()),
  api: { delete: excluir },
}));

import {
  _definirEstadoParaTestes,
  _reiniciarProjetosParaTestes,
  capturarSnapshot,
  lerEstado,
  limparTudo,
} from '../projetos';

afterEach(() => { excluir.mockClear(); _reiniciarProjetosParaTestes(); });

describe('apagar todos os dados', () => {
  it('remove conversas e agentes individuais no backend antes de limpar a tela', async () => {
    const base = capturarSnapshot();
    _definirEstadoParaTestes({
      ...base,
      projetos: [{
        id: 'projeto-1', tipo: 'projeto', titulo: 'Projeto', pedido: '', modelo: '', assunto: '',
        resposta: '', criadoEm: 1, tarefas: [], agenteIds: [], entregas: {},
        marcos: { plano: 1, nascimentos: [], trabalho: 1, fim: 0 }, versao: 1,
      }],
      agentes: {
        'agente-1': {
          id: 'agente-1', projetoId: '', conversaId: 'conversa-agente-1', nome: 'Ravi', funcao: 'Texto',
          cor: '#56A8FF', tipoMovimento: 'ondas', ferramentas: [], status: 'aguardando', verbo: 'Escrevendo',
          espera: 'Aguardando', instrucoes: '', avulso: true, criadoEm: 1,
        },
      },
    });

    await limparTudo();

    expect(excluir.mock.calls.map(([caminho]) => caminho)).toEqual([
      '/v1/conversas/projeto-1?manter_agentes=false',
      '/v1/conversas/conversa-agente-1?manter_agentes=false',
      '/v1/agentes/agente-1',
    ]);
    expect(lerEstado().projetos).toEqual([]);
    expect(lerEstado().agentes).toEqual({});
  });
});
