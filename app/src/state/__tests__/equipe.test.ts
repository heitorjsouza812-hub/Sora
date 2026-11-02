import { describe, expect, it } from 'vitest';
import { aplicarEventoEquipe, chaveContexto, equipeInicial } from '../equipe';
import { aplicarEvento } from '../aplicarEvento';
import type { EstadoProjetos } from '../projetos';

const ev = (tipo: string, dados: Record<string, unknown>) => ({ tipo, dados });
const A = 'a-1';

describe('eventos de equipe (contrato do Tear, Âncora e Leme)', () => {
  it('canal.mensagem é idempotente e ordena por seq', () => {
    let e = equipeInicial();
    const m = (id: string, seq: number) => ev('canal.mensagem', { canal_id: 'c', mensagem_id: id, seq, autor: 'agente', agente_id: A, tipo: 'mensagem', texto: id, anexos: [], criada_em: '2026-11-02T10:00:00Z' });
    e = aplicarEventoEquipe(e, m('m2', 2)); e = aplicarEventoEquipe(e, m('m1', 1)); e = aplicarEventoEquipe(e, m('m2', 2));
    expect(e.mensagens.c.map(x => x.id)).toEqual(['m1', 'm2']);
  });

  it('canal.tarefa antigo não desfaz revisão mais nova', () => {
    const t = (revisao: number, status: string) => ev('canal.tarefa', { canal_id: 'c', tarefa_id: 't', dono_id: A, status, revisao, acoes: status === 'rodando' ? ['parar', 'cancelar'] : ['retomar'] });
    let e = aplicarEventoEquipe(equipeInicial(), t(2, 'parada'));
    e = aplicarEventoEquipe(e, t(1, 'rodando'));
    expect(e.tarefas.t.status).toBe('parada');
    expect(e.tarefas.t.acoes).toEqual(['retomar']);
  });

  it('fila, contexto e canal.atualizado entram no estado', () => {
    let e = aplicarEventoEquipe(equipeInicial(), ev('fila.atualizada', { agente_id: A, pausada: true, limite_tarefas: 2, itens: [{ item_id: 'i', seq: 1, pista: 'p', origem: 'usuario', previa: 'oi', status: 'na_fila' }] }));
    e = aplicarEventoEquipe(e, ev('contexto.atualizado', { agente_id: A, fio: 'principal', porcentagem: 82, tokens: 10, janela: 12, estimado: false, nivel: 'compactar', compactacao: 'compactando' }));
    e = aplicarEventoEquipe(e, ev('canal.atualizado', { canal_id: 'c', nome: 'Lançamento', membros: [A], lider_id: A, arquivado: false }));
    expect(e.filas[A].pausada).toBe(true); expect(e.filas[A].itens[0].previa).toBe('oi');
    expect(e.contextos[chaveContexto(A, 'principal')]).toMatchObject({ porcentagem: 82, nivel: 'compactar', compactacao: 'compactando' });
    expect(e.canais.c).toMatchObject({ nome: 'Lançamento', liderId: A });
  });

  it('reação liga e desliga; navegador.aba abre, atualiza e fecha', () => {
    let e = aplicarEventoEquipe(equipeInicial(), ev('reacao', { mensagem_id: 'm', emoji: '👍', autor: 'usuario', ligada: true }));
    expect(e.reacoes.m).toEqual({ '👍': 1 });
    e = aplicarEventoEquipe(e, ev('reacao', { mensagem_id: 'm', emoji: '👍', autor: 'usuario', ligada: false }));
    expect(e.reacoes.m).toEqual({});
    e = aplicarEventoEquipe(e, ev('navegador.aba', { aba_id: 'x', agente_id: A, url: 'https://a.com', titulo: 'A', carregada: true, assumida_pelo_usuario: false, pedido_de_ajuda: 'captcha' }));
    expect(e.abas.x.pedidoDeAjuda).toBe('captcha');
    e = aplicarEventoEquipe(e, ev('navegador.aba', { aba_id: 'x', agente_id: A, url: '', titulo: '', carregada: true, assumida_pelo_usuario: false, fechada: true }));
    expect(e.abas).toEqual({});
  });

  it('evento desconhecido devolve o mesmo estado', () => {
    const e = equipeInicial();
    expect(aplicarEventoEquipe(e, ev('outra.coisa', {}))).toBe(e);
  });

  it('aprovacao.pedida com tipo aprovar_dominio vira cartão de domínio', () => {
    const base = { versao: 2, projetos: [], agentes: {}, execucoes: [], mensagens: [], pendencias: [] } as unknown as EstadoProjetos;
    const r = aplicarEvento(base, { id: '1-0', tipo: 'aprovacao.pedida', recebidoEm: 1, dados: {
      conversa_id: 'c', aprovacao_id: 'ap', resumo: 'Abrir banco.com', dano: '', quem_recebe: null, expira_em: '2026-11-02T10:00:00Z', tipo: 'aprovar_dominio',
      dominio: 'banco.com', url: 'https://banco.com/x', perfil: { tipo: 'perfil', nome: 'Trabalho' }, agente_id: A, opcoes: [{ rotulo: 'Aprovar domínio', valor: 'sempre_permitir' }, { rotulo: 'Negar', valor: 'negar' }],
    } });
    const p = r.pendencias![0];
    expect(p.tipo === 'aprovacao' && p.revisaoDominio).toMatchObject({ dominio: 'banco.com', perfil: { nome: 'Trabalho' }, agenteId: A });
  });
});
