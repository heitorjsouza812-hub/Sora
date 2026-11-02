import { beforeEach, describe, expect, it, vi } from 'vitest';
import { aplicarEvento } from '../aplicarEvento';
import { horarioDoEvento, type EventoSse } from '../../api/eventos';
import type { EstadoProjetos } from '../projetos';

const AGORA = 1_700_000_000_000;
const conversaId = '00000000-0000-0000-0000-000000000001';
const agenteId = '00000000-0000-0000-0000-000000000002';
const etapaId = '00000000-0000-0000-0000-000000000003';

function estado(): EstadoProjetos {
  return {
    versao: 2, sora: { nome: 'Sora', cor: '#E2ECFF' }, agentes: {}, projetoAtivoId: conversaId,
    projetos: [{
      id: conversaId, tipo: 'chat', titulo: 'Campanha', pedido: 'Crie uma campanha', modelo: '', assunto: 'Campanha', resposta: '', criadoEm: AGORA,
      tarefas: [], agenteIds: [], entregas: {}, marcos: { plano: AGORA, nascimentos: [], trabalho: AGORA, fim: AGORA }, aprovadaVersao: null, versao: 1,
    }],
    execucoes: [], mensagens: [], pluginsConectados: [], carregando: false,
  };
}

function evento(tipo: string, dados: Record<string, unknown>, deslocamento = 0): EventoSse {
  return { id: `${AGORA + deslocamento}-0`, tipo, dados: { conversa_id: conversaId, ...dados }, recebidoEm: AGORA + deslocamento };
}

beforeEach(() => vi.setSystemTime(AGORA));

describe('aplicarEvento', () => {
  it('monta plano, agente e execução somente a partir dos eventos do backend', () => {
    let e = aplicarEvento(estado(), evento('agente.criado', { agente_id: agenteId, tipo: 'especialista', nome: 'Atlas', funcao: 'Pesquisa', cor: '#56A8FF', movimento: 'vibracao' }));
    e = aplicarEvento(e, evento('cadeia.criada', { cadeia_id: 'cadeia-1', versao: 1, etapas: [{ etapa_id: etapaId, ordem: 1, especialista: 'pesquisador', agente_id: agenteId, titulo: 'Pesquisar referências', nivel: 'N1', depende_de: [] }] }, 1));

    expect(e.agentes[agenteId]).toMatchObject({ nome: 'Atlas', projetoId: conversaId, avulso: false });
    expect(e.projetos[0]).toMatchObject({ cadeiaId: 'cadeia-1', cadeiaStatus: 'planejando', agenteIds: [agenteId] });
    expect(e.projetos[0]?.tarefas[0]).toMatchObject({ id: etapaId, agenteId, progresso: 0 });
    expect(e.execucoes[0]).toMatchObject({ id: etapaId, agenteId, status: 'pendente' });
  });

  it('atualiza progresso e passos sem avançar por relógio', () => {
    let e = aplicarEvento(estado(), evento('cadeia.criada', { cadeia_id: 'cadeia-1', versao: 1, etapas: [{ etapa_id: etapaId, ordem: 1, agente_id: agenteId, titulo: 'Pesquisar', depende_de: [] }] }));
    e = aplicarEvento(e, evento('etapa.atualizada', { etapa_id: etapaId, status: 'executando', progresso: 45, tokens: 10, custo_usd: 0 }, 10));
    e = aplicarEvento(e, evento('passo', { passo_id: 'passo-1', etapa_id: etapaId, agente_id: agenteId, tipo: 'ferramenta', texto: 'Buscando', ferramenta: 'buscar_web', acao: 'buscar_web', parametros: { consulta: 'café' }, resultado: null, status: 'executando', para_agente_id: null }, 20));

    expect(e.execucoes[0]).toMatchObject({ status: 'executando', progresso: 45 });
    expect(e.execucoes[0]?.roteiro[0]).toMatchObject({ id: 'passo-1', status: 'executando', ferramenta: 'buscar_web' });

    const muitoDepois = aplicarEvento(e, evento('ping', {}, 999_999));
    expect(muitoDepois.execucoes[0]).toMatchObject({ status: 'executando', progresso: 45 });
  });

  it('concatena deltas SSE e encerra a mensagem pelo evento fim', () => {
    let e = aplicarEvento(estado(), evento('mensagem.inicio', { mensagem_id: 'msg-1', autor: 'sora', agente_id: agenteId }));
    e = aplicarEvento(e, evento('mensagem.delta', { mensagem_id: 'msg-1', texto: 'Tudo ' }, 1));
    e = aplicarEvento(e, evento('mensagem.delta', { mensagem_id: 'msg-1', texto: 'pronto.' }, 2));
    e = aplicarEvento(e, evento('mensagem.fim', { mensagem_id: 'msg-1', anexos: [] }, 3));
    expect(e.mensagens).toEqual([expect.objectContaining({ id: 'msg-1', texto: 'Tudo pronto.', gerando: false })]);
  });

  it('mensagem.fim limpa o "pensando" quando a triagem falha e só há mensagem.*', () => {
    let e = aplicarEvento({ ...estado(), projetos: [{ ...estado().projetos[0]!, mensagensPendentes: true }] }, evento('mensagem.inicio', { mensagem_id: 'aviso', autor: 'sora' }));
    expect(e.projetos[0]?.mensagensPendentes).toBe(true);
    e = aplicarEvento(e, evento('mensagem.delta', { mensagem_id: 'aviso', texto: 'Não consegui falar com o seu modelo.' }, 1));
    e = aplicarEvento(e, evento('mensagem.fim', { mensagem_id: 'aviso' }, 2));
    expect(e.projetos[0]?.mensagensPendentes).toBe(false);
  });

  it('pergunta e aprovação viram pendências; resolvida e progresso da cadeia as limpam', () => {
    let e = aplicarEvento(estado(), evento('pergunta', { pergunta_id: 'p1', texto: 'Continuar?', opcoes: [{ rotulo: 'Continuar', valor: 'continuar' }, { rotulo: 'Parar', valor: 'parar' }], resposta_livre: false }));
    e = aplicarEvento(e, evento('pergunta', { pergunta_id: 'p1', texto: 'Continuar?', opcoes: [], resposta_livre: false }, 1));
    e = aplicarEvento(e, evento('aprovacao.pedida', { aprovacao_id: 'a1', resumo: 'Criar o agente Íris', dano: 'Passa a usar ferramentas', quem_recebe: null, expira_em: '2030-01-01T00:00:00Z' }, 2));
    expect(e.pendencias?.map(x => [x.tipo, x.id])).toEqual([['pergunta', 'p1'], ['aprovacao', 'a1']]);
    expect(e.pendencias?.[0]).toMatchObject({ opcoes: [{ rotulo: 'Continuar', valor: 'continuar' }, { rotulo: 'Parar', valor: 'parar' }] });
    e = aplicarEvento(e, evento('aprovacao.resolvida', { aprovacao_id: 'a1', status: 'permitida' }, 3));
    expect(e.pendencias?.map(x => x.id)).toEqual(['p1']);
    e = aplicarEvento(e, evento('cadeia.atualizada', { cadeia_id: 'c', status: 'aguardando_usuario', tokens_usados: 0, custo_usd: 0 }, 4));
    expect(e.pendencias).toHaveLength(1);
    e = aplicarEvento(e, evento('cadeia.atualizada', { cadeia_id: 'c', status: 'executando', tokens_usados: 0, custo_usd: 0 }, 5));
    expect(e.pendencias).toHaveLength(0);
  });

  it('usa o relógio do servidor (id do Redis Stream) como horário do evento', () => {
    expect(horarioDoEvento('1730518324070-3')).toBe(1730518324070);
    vi.setSystemTime(AGORA);
    expect(horarioDoEvento('0-0')).toBe(AGORA);
  });

  it('nova tentativa reemite a cadeia com outro etapa_id na mesma ordem e vale a mais recente', () => {
    const nova = '00000000-0000-0000-0000-000000000009';
    let e = aplicarEvento(estado(), evento('cadeia.criada', { cadeia_id: 'cadeia-1', versao: 1, etapas: [
      { etapa_id: etapaId, ordem: 1, agente_id: agenteId, titulo: 'Pesquisar', depende_de: [] },
      { etapa_id: 'v1', ordem: 2, agente_id: agenteId, titulo: 'Verificar', depende_de: [1] }] }));
    e = aplicarEvento(e, evento('cadeia.criada', { cadeia_id: 'cadeia-1', versao: 1, etapas: [{ etapa_id: nova, ordem: 1, agente_id: agenteId, titulo: 'Pesquisar', depende_de: [] }] }, 5));
    expect(e.projetos[0]?.tarefas.map(t => [t.ordem, t.id])).toEqual([[1, nova], [2, 'v1']]);
    const outra = aplicarEvento(e, evento('cadeia.criada', { cadeia_id: 'cadeia-2', versao: 2, etapas: [{ etapa_id: 'a2', ordem: 1, agente_id: agenteId, titulo: 'Ajuste', depende_de: [] }] }, 9));
    expect(outra.projetos[0]?.tarefas.map(t => t.id)).toEqual(['a2']);
  });

  it('aprovacao.resolvida de um pedido que não está na tela não muda nada', () => {
    const e = aplicarEvento(estado(), evento('aprovacao.resolvida', { aprovacao_id: 'x', status: 'expirada' }));
    expect(e.pendencias ?? []).toEqual([]);
    expect(e.projetos).toEqual(estado().projetos);
  });

  it('não duplica o texto quando o SSE repete a mensagem já carregada do histórico', () => {
    const base = estado();
    let e: EstadoProjetos = { ...base, mensagens: [{ id: 'msg-1', conversaId, autor: 'sora', texto: 'Tudo pronto.', criadoEm: AGORA, gerando: false }] };
    e = aplicarEvento(e, evento('mensagem.inicio', { mensagem_id: 'msg-1', autor: 'sora' }));
    e = aplicarEvento(e, evento('mensagem.delta', { mensagem_id: 'msg-1', texto: 'Tudo pronto.' }, 1));
    e = aplicarEvento(e, evento('mensagem.fim', { mensagem_id: 'msg-1', anexos: [] }, 2));
    expect(e.mensagens).toHaveLength(1);
    expect(e.mensagens[0]?.texto).toBe('Tudo pronto.');
  });

  it('é idempotente para passo e entrega repetidos na retomada', () => {
    let e = aplicarEvento(estado(), evento('cadeia.criada', { cadeia_id: 'cadeia-1', versao: 1, etapas: [{ etapa_id: etapaId, ordem: 1, agente_id: agenteId, titulo: 'Pesquisar', depende_de: [] }] }));
    const passo = evento('passo', { passo_id: 'passo-1', etapa_id: etapaId, agente_id: agenteId, tipo: 'entrega', texto: 'Entregou', resultado: { resumo: '4 links' }, status: 'concluido' });
    const entrega = evento('entrega', { entrega_id: 'entrega-1', agente_id: agenteId, versao: 1, tipo: 'links', titulo: 'Pesquisa', resumo: '4 links' });
    e = aplicarEvento(aplicarEvento(e, passo), passo);
    e = aplicarEvento(aplicarEvento(e, entrega), entrega);
    expect(e.execucoes[0]?.roteiro).toHaveLength(1);
    expect(Object.values(e.projetos[0]!.entregas)).toHaveLength(1);
  });

  it('marca a cadeia concluída e a conversa aprovada por eventos reais', () => {
    let e = aplicarEvento(estado(), evento('cadeia.atualizada', { cadeia_id: 'cadeia-1', status: 'concluida', tokens_usados: 20, custo_usd: 0 }));
    e = aplicarEvento(e, evento('conversa.atualizada', { conversa_id: conversaId, titulo: 'Campanha final', tipo: 'projeto', aprovada_versao: 1 }, 1));
    expect(e.projetos[0]).toMatchObject({ titulo: 'Campanha final', tipo: 'projeto', cadeiaStatus: 'concluida', aprovadaVersao: 1 });
    expect(e.projetos[0]?.aprovadoEm).toBe(AGORA + 1);
  });
});
