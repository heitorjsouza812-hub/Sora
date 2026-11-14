import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const listarGrupos = vi.hoisted(() => vi.fn());
vi.mock('../../api/grupos', async (importar) => {
  const original = await importar<typeof import('../../api/grupos')>();
  return { ...original, listarGrupos };
});

import { _reiniciarAtencaoParaTestes, lerPrecisaDeVoce } from '../atencao';
import { _reiniciarGruposParaTestes, estadoDoMembro, lerGrupos, receberEventoGrupos, receberGrupo } from '../grupos';

const grupo = (id: string, nome: string, extra: Record<string, unknown> = {}) => ({ id, nome, membros: ['sora', 'b1', 'b2'], liderId: 'sora', precisaDeVoce: false, trabalhando: false, ...extra });
const atualizado = (dados: Record<string, unknown>) => ({ tipo: 'canal.atualizado', dados: { membros: [], ...dados } });

describe('estado de grupos por SSE', () => {
  beforeEach(() => { vi.useFakeTimers(); listarGrupos.mockReset(); _reiniciarGruposParaTestes(); _reiniciarAtencaoParaTestes(); });
  afterEach(() => { vi.useRealTimers(); });

  it('canal.mensagem é idempotente', () => {
    const evento = { tipo: 'canal.mensagem', dados: { canal_id: 'g1', mensagem_id: 'm1', seq: 1, autor: 'agente', agente_id: 'b1', tipo: 'resultado', texto: 'Pronto', anexos: [], criada_em: '' } };
    receberEventoGrupos(evento); receberEventoGrupos(evento);
    expect(lerGrupos().mensagens.g1).toHaveLength(1);
  });

  it('canal.atualizado não aplica o conteúdo (histórico reentregue): relê GET /v1/grupos uma vez', async () => {
    listarGrupos.mockResolvedValue([grupo('g1', 'Produto', { trabalhando: true })]);
    receberEventoGrupos(atualizado({ canal_id: 'g1', nome: 'Nome antigo', estado: 'precisa_de_voce' }));
    receberEventoGrupos(atualizado({ canal_id: 'g1', nome: 'Produto', estado: 'trabalhando' }));
    expect(lerGrupos().lista).toEqual([]); // nada pisca antes da releitura
    await vi.advanceTimersByTimeAsync(500);
    expect(listarGrupos).toHaveBeenCalledTimes(1);
    expect(lerGrupos().lista).toEqual([expect.objectContaining({ id: 'g1', nome: 'Produto', trabalhando: true, precisaDeVoce: false })]);
  });

  it('grupo arquivado sai na hora e não volta pela reentrega', async () => {
    receberGrupo(grupo('g1', 'QA'));
    listarGrupos.mockResolvedValue([]);
    receberEventoGrupos(atualizado({ canal_id: 'g1', nome: 'QA', arquivado: true }));
    expect(lerGrupos().lista).toEqual([]);
    receberEventoGrupos(atualizado({ canal_id: 'g2', nome: 'Antigo', arquivado: true }));
    await vi.advanceTimersByTimeAsync(500);
    expect(lerGrupos().lista).toEqual([]);
  });

  it('releitura pedida durante uma leitura em voo não se perde', async () => {
    let soltar: (valor: unknown) => void = () => undefined;
    listarGrupos.mockImplementationOnce(() => new Promise(resolve => { soltar = resolve; }));
    listarGrupos.mockResolvedValueOnce([grupo('g1', 'Novo')]);
    receberEventoGrupos(atualizado({ canal_id: 'g1', nome: 'Novo' }));
    await vi.advanceTimersByTimeAsync(500); // 1ª leitura em voo (resposta velha)
    receberEventoGrupos(atualizado({ canal_id: 'g1', nome: 'Novo' }));
    await vi.advanceTimersByTimeAsync(500); // pedido durante o voo fica pendente
    soltar([]);
    await vi.advanceTimersByTimeAsync(0);
    await vi.waitFor(() => expect(lerGrupos().lista.map(item => item.nome)).toEqual(['Novo']));
    expect(listarGrupos).toHaveBeenCalledTimes(2);
  });

  it('precisa_de_voce.atualizado reentregue não aplica pedidos antigos (só a releitura da atenção vale)', () => {
    receberEventoGrupos({ tipo: 'precisa_de_voce.atualizado', dados: { grupo_id: 'g1', estado: 'precisa_de_voce', pedidos: [{ id: 'p1', tipo: 'aprovacao', grupo_id: 'g1', titulo: 'Aprovar acesso', resumo: 'Abrir ferramenta' }] } });
    expect(lerPrecisaDeVoce().lista).toEqual([]);
  });

  it('canal.tarefa dá o estado do membro e não volta para uma revisão antiga', () => {
    const tarefa = (status: string, revisao: number) => ({ tipo: 'canal.tarefa', dados: { canal_id: 'g1', tarefa_id: 't1', dono_id: 'b1', status, revisao, acoes: [] } });
    expect(estadoDoMembro(lerGrupos().tarefas.g1, 'b1')).toBe('livre');
    receberEventoGrupos(tarefa('rodando', 1));
    expect(estadoDoMembro(lerGrupos().tarefas.g1, 'b1')).toBe('trabalhando');
    receberEventoGrupos(tarefa('parada', 2));
    receberEventoGrupos(tarefa('rodando', 1));
    expect(estadoDoMembro(lerGrupos().tarefas.g1, 'b1')).toBe('parado');
    expect(estadoDoMembro(lerGrupos().tarefas.g1, 'b2')).toBe('livre');
    receberEventoGrupos(tarefa('concluida', 3));
    expect(estadoDoMembro(lerGrupos().tarefas.g1, 'b1')).toBe('livre');
  });
});
