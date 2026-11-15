import { beforeEach, describe, expect, it, vi } from 'vitest';

const get = vi.hoisted(() => vi.fn());
const post = vi.hoisted(() => vi.fn());
const patch = vi.hoisted(() => vi.fn());
vi.mock('../cliente', () => ({ api: { get, post, patch } }));

import { criarGrupo, enviarMensagemGrupo, grupoDaApi, listarGrupos, mensagemDaApi, pararBotNoGrupo, pedidoDaApi, resolverPedidoAtencao } from '../grupos';

describe('adaptador da API de grupos', () => {
  beforeEach(() => { get.mockReset(); post.mockReset(); patch.mockReset(); });
  it('normaliza GrupoSaida e estado de atenção', () => {
    expect(grupoDaApi({ id: 'g1', nome: 'Lançamento', membros: ['b1', { id: 'b2' }], estado: 'precisa_de_voce' })).toEqual({
      id: 'g1', nome: 'Lançamento', membros: ['b1', 'b2'], liderId: null, precisaDeVoce: true, trabalhando: false,
    });
  });

  it('normaliza repasse e anexos sem inventar conteúdo', () => {
    const mensagem = mensagemDaApi({ canal_id: 'g1', mensagem_id: 'm1', seq: 4, autor: 'agente', agente_id: 'b1', tipo: 'atividade', texto: 'Passei a pesquisa.', responde_a: 'm0', anexos: [{ id: 'a1', nome: 'Pesquisa.pdf', url: '/v1/anexos/a1' }], criada_em: '2026-11-04T22:00:00Z' });
    expect(mensagem).toMatchObject({ id: 'm1', grupoId: 'g1', autor: 'bot', botId: 'b1', tipo: 'repasse', respondeA: 'm0' });
    expect(mensagem.anexos).toEqual([{ id: 'a1', nome: 'Pesquisa.pdf' }]);
  });

  it('aceita anexos como UUID puro, que é o formato do canal.mensagem', () => {
    const mensagem = mensagemDaApi({ canal_id: 'g1', mensagem_id: 'm2', seq: 5, autor: 'agente', agente_id: 'b1', tipo: 'resultado', texto: 'Pronto.', anexos: ['a2', 'a3', ''], criada_em: '2026-11-04T22:00:00Z' });
    expect(mensagem.tipo).toBe('resultado');
    expect(mensagem.anexos).toEqual([{ id: 'a2', nome: 'Arquivo 1' }, { id: 'a3', nome: 'Arquivo 2' }]);
  });

  it('lê tarefas do grupo e o retorno do Parar', async () => {
    post.mockResolvedValueOnce([{ canal_id: 'g1', tarefa_id: 't1', dono_id: 'b1', status: 'parada', revisao: 3, acoes: ['retomar'] }]);
    await expect(pararBotNoGrupo('g1', 'b1')).resolves.toEqual([{ id: 't1', grupoId: 'g1', donoId: 'b1', status: 'parada', revisao: 3, paiId: null, motivo: null, acoes: ['retomar'] }]);
    expect(post).toHaveBeenCalledWith('/v1/grupos/g1/membros/b1/parar');
  });

  it('converte rascunho de envio no cartão Enviar/Descartar', () => {
    // `acao` é o id técnico da ferramenta: o cartão mostra só o resumo em PT-BR.
    expect(pedidoDaApi({ id: 'p1', tipo: 'rascunho_envio', agente_id: 'b1', grupo_id: 'g1', titulo: 'Revisar envio', resumo: 'Para a cliente · proposta', acao: 'gmail_enviar', opcoes: [{ rotulo: 'Enviar', valor: 'permitir' }, { rotulo: 'Descartar', valor: 'negar' }] })).toMatchObject({
      id: 'p1', tipo: 'envio', botId: 'b1', grupoId: 'g1', titulo: 'Revisar envio', resumo: 'Para a cliente · proposta', detalhes: null,
    });
  });

  it('usa as rotas reais de grupos e mantém resposta/destinatário na mensagem', async () => {
    get.mockResolvedValue([]);
    post.mockResolvedValueOnce({ id: 'g1', nome: 'Equipe', membros: ['sora', 'b1', 'b2'], estado: 'livre' })
      .mockResolvedValueOnce({ canal_id: 'g1', mensagem_id: 'm1', seq: 1, autor: 'usuario', texto: 'Oi', anexos: [] })
      .mockResolvedValueOnce([]);
    await listarGrupos();
    await criarGrupo({ nome: 'Equipe', membros: ['b1', 'b2'] });
    await enviarMensagemGrupo('g1', { texto: 'Oi', destinatario: 'b1', respondeA: 'm0' });
    await pararBotNoGrupo('g1', 'b1');
    expect(get).toHaveBeenCalledWith('/v1/grupos?arquivados=false');
    expect(post).toHaveBeenNthCalledWith(1, '/v1/grupos', { nome: 'Equipe', membros: ['b1', 'b2'] });
    expect(post).toHaveBeenNthCalledWith(2, '/v1/canais-equipe/g1/mensagens', { texto: 'Oi', destinatario: 'b1', responde_a: 'm0', anexos: [] });
    expect(post).toHaveBeenNthCalledWith(3, '/v1/grupos/g1/membros/b1/parar');
  });

  it('resolve pergunta e aprovação nos endpoints canônicos', async () => {
    post.mockResolvedValue(undefined);
    await resolverPedidoAtencao({ id: 'p', tipo: 'pergunta', titulo: '', resumo: '' }, 'responder', 'sim');
    await resolverPedidoAtencao({ id: 'a', tipo: 'aprovacao', titulo: '', resumo: '' }, 'recusar');
    expect(post).toHaveBeenNthCalledWith(1, '/v1/perguntas/p/responder', { valor: 'sim' });
    expect(post).toHaveBeenNthCalledWith(2, '/v1/aprovacoes/a/decidir', { decisao: 'negar' });
  });
});
