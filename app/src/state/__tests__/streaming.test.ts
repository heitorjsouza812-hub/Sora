import { beforeEach, describe, expect, it, vi } from 'vitest';
import { aplicarEvento, registrarEnvioDoUsuario } from '../aplicarEvento';
import type { EventoSse } from '../../api/eventos';
import { gerandoNa, type EstadoProjetos } from '../projetos';

const AGORA = 1_700_000_000_000;
const conversaId = '00000000-0000-0000-0000-000000000001';
const soraId = '00000000-0000-0000-0000-0000000000aa';
const botId = '00000000-0000-0000-0000-0000000000bb';

function estado(): EstadoProjetos {
  return {
    versao: 2, sora: { nome: 'Sora', cor: '#E2ECFF' }, agentes: { [botId]: { id: botId, projetoId: '', conversaId, nome: 'Maquina', funcao: 'Bot', cor: '#56A8FF', tipoMovimento: 'gira', ferramentas: [], status: 'aguardando', verbo: 'Trabalhando', espera: 'Aguardando', instrucoes: '', avulso: true, criadoEm: AGORA } },
    projetoAtivoId: conversaId,
    projetos: [{ id: conversaId, tipo: 'chat', titulo: 'Conversa', pedido: '', modelo: '', assunto: '', resposta: '', criadoEm: AGORA, tarefas: [], agenteIds: [], entregas: {}, marcos: { plano: AGORA, nascimentos: [], trabalho: AGORA, fim: 0 }, aprovadaVersao: null, versao: 1 }],
    execucoes: [], mensagens: [], pluginsConectados: [], carregando: false,
  };
}
let n = 0;
const ev = (tipo: string, dados: Record<string, unknown>): EventoSse => { n += 1; return { id: `${AGORA + n}-0`, tipo, dados: { conversa_id: conversaId, ...dados }, recebidoEm: AGORA + n }; };
const token = (fluxo: string, texto: string, extra: Record<string, unknown> = {}) => ev('mensagem.token', { fluxo_id: fluxo, agente_id: soraId, canal_id: null, texto, fim: false, ...extra });

beforeEach(() => { n = 0; });

describe('mensagem.token (prévia ao vivo)', () => {
  it('substitui o texto acumulado, sem concatenar, numa bolha só por fluxo', () => {
    let e = aplicarEvento(estado(), token('f1', 'Olá'));
    e = aplicarEvento(e, token('f1', 'Olá, tudo'));
    e = aplicarEvento(e, token('f1', 'Olá, tudo bem?'));
    expect(e.mensagens).toHaveLength(1);
    expect(e.mensagens[0]).toMatchObject({ id: 'previa:f1', texto: 'Olá, tudo bem?', gerando: true, previa: true, autor: 'sora', conversaId });
  });

  it('prévia de bot usa o id do bot como autor', () => {
    const e = aplicarEvento(estado(), token('f1', 'Oi', { agente_id: botId }));
    expect(e.mensagens[0]).toMatchObject({ autor: botId, agenteId: botId });
  });

  it('fim=true remove a prévia e token atrasado não a ressuscita', () => {
    let e = aplicarEvento(estado(), token('f1', 'Olá'));
    e = aplicarEvento(e, token('f1', '', { fim: true }));
    expect(e.mensagens).toHaveLength(0);
    e = aplicarEvento(e, token('f1', 'Olá de novo'));
    expect(e.mensagens).toHaveLength(0);
  });

  it('a mensagem oficial substitui a prévia sem duplicar, mesmo sem fim', () => {
    let e = aplicarEvento(estado(), token('f1', 'A capital da França é Paris.'));
    e = aplicarEvento(e, ev('mensagem.inicio', { mensagem_id: 'm1', autor: 'sora', agente_id: soraId }));
    expect(e.mensagens.map(m => m.id)).toEqual(['m1']);
    e = aplicarEvento(e, ev('mensagem.delta', { mensagem_id: 'm1', texto: 'A capital da França é Paris.' }));
    e = aplicarEvento(e, ev('mensagem.fim', { mensagem_id: 'm1' }));
    expect(e.mensagens).toHaveLength(1);
    expect(e.mensagens[0]).toMatchObject({ id: 'm1', texto: 'A capital da França é Paris.', gerando: false });
  });

  it('prévia sem conversa explícita ou de grupo (canal_id) não entra na conversa ativa', () => {
    const semConversa: EventoSse = { id: `${AGORA}-9`, tipo: 'mensagem.token', dados: { fluxo_id: 'f2', agente_id: botId, canal_id: null, texto: 'x', fim: false }, recebidoEm: AGORA };
    expect(aplicarEvento(estado(), semConversa).mensagens).toHaveLength(0);
    expect(aplicarEvento(estado(), token('f3', 'x', { canal_id: 'canal-1' })).mensagens).toHaveLength(0);
  });

  it('eco do envio do usuário não cria bolha a mais quando a prévia já está na tela', () => {
    let e = aplicarEvento(estado(), token('f1', 'Resposta'));
    e = registrarEnvioDoUsuario(e, { id: 'u1', conversaId, texto: 'Pergunta', enviadoEm: AGORA - 5 });
    e = registrarEnvioDoUsuario(e, { id: 'u1', conversaId, texto: 'Pergunta', enviadoEm: AGORA - 5 });
    expect(e.mensagens.filter(m => m.autor === 'usuario')).toHaveLength(1);
  });
});

describe('cartão de aprovação da cadeia na conversa', () => {
  const aprovacao = (extra: Record<string, unknown> = {}) => ev('aprovacao.pedida', { aprovacao_id: 'a1', resumo: 'Abrir python.org', dano: '', quem_recebe: null, tipo: 'aprovar_dominio', dominio: 'python.org', url: 'https://python.org', bot_id: botId, grupo_id: null, expira_em: '2030-01-01T00:00:00Z', ...extra });

  it('vira pendência da conversa (aparece no chat) e a resolução expirada a remove', () => {
    let e = aplicarEvento(estado(), aprovacao());
    expect(e.pendencias).toHaveLength(1);
    expect(e.pendencias?.[0]).toMatchObject({ id: 'a1', conversaId, tipo: 'aprovacao' });
    e = aplicarEvento(e, ev('aprovacao.resolvida', { aprovacao_id: 'a1', status: 'expirada' }));
    expect(e.pendencias).toHaveLength(0);
  });

  it('o mesmo evento repetido pelo SSE não duplica o cartão', () => {
    let e = aplicarEvento(estado(), aprovacao());
    e = aplicarEvento(e, aprovacao());
    expect(e.pendencias).toHaveLength(1);
  });
});

describe('falha da cadeia', () => {
  it('a mensagem de falha da Sora tira a conversa de "pensando"', () => {
    let e = aplicarEvento(estado(), ev('roteamento', { modo: 'cadeia' }));
    e = aplicarEvento(e, ev('mensagem.inicio', { mensagem_id: 'f1', autor: 'sora', agente_id: soraId }));
    e = aplicarEvento(e, ev('mensagem.delta', { mensagem_id: 'f1', texto: 'Não consegui concluir o trabalho.' }));
    e = aplicarEvento(e, ev('mensagem.fim', { mensagem_id: 'f1' }));
    e = aplicarEvento(e, ev('cadeia.atualizada', { cadeia_id: 'c1', status: 'falhou' }));
    expect(e.mensagens.at(-1)).toMatchObject({ texto: 'Não consegui concluir o trabalho.', gerando: false });
    expect(e.projetos[0]).toMatchObject({ cadeiaStatus: 'falhou', mensagensPendentes: false });
  });
});

describe('lote por quadro (receber)', () => {
  it('várias prévias no mesmo quadro viram uma atualização só, com o último texto', async () => {
    vi.useFakeTimers();
    const { _aplicarEventoParaTestes, _definirEstadoParaTestes, lerEstado, _reiniciarProjetosParaTestes } = await import('../projetos');
    _definirEstadoParaTestes(estado());
    _aplicarEventoParaTestes(token('fl', 'A'));
    _aplicarEventoParaTestes(token('fl', 'AB'));
    _aplicarEventoParaTestes(token('fl', 'ABC'));
    expect(lerEstado().mensagens).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(40);
    expect(lerEstado().mensagens.map(m => m.texto)).toEqual(['ABC']);
    _aplicarEventoParaTestes(token('fl', 'ABCD'));
    _aplicarEventoParaTestes(token('fl', '', { fim: true }));
    expect(lerEstado().mensagens).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(40);
    expect(lerEstado().mensagens).toHaveLength(0);
    _reiniciarProjetosParaTestes();
    vi.useRealTimers();
  });
});

describe('resposta direta: a resposta é a única mensagem (sem confirmação)', () => {
  it('roteamento direto, uma mensagem e fim: encerra o turno sem esperar segunda mensagem', () => {
    let e = aplicarEvento(estado(), ev('roteamento', { modo: 'direto' }));
    expect(gerandoNa(e, conversaId, AGORA + 5_000)).toBe(true);
    e = aplicarEvento(e, ev('mensagem.inicio', { mensagem_id: 'resp', autor: 'sora', agente_id: soraId }));
    expect(gerandoNa(e, conversaId, AGORA + 5_000)).toBe(true);
    e = aplicarEvento(e, ev('mensagem.delta', { mensagem_id: 'resp', texto: 'A capital da França é Paris.' }));
    e = aplicarEvento(e, ev('mensagem.fim', { mensagem_id: 'resp' }));
    expect(e.mensagens.at(-1)).toMatchObject({ texto: 'A capital da França é Paris.', gerando: false });
    expect(e.projetos[0].aguardaRespostaDesde).toBeUndefined();
    expect(gerandoNa(e, conversaId, AGORA + 5_000)).toBe(false);
  });

  it('cadeia: a confirmação não encerra o turno; o trabalho segue até a cadeia terminar', () => {
    let e = aplicarEvento(estado(), ev('roteamento', { modo: 'cadeia' }));
    e = aplicarEvento(e, ev('mensagem.inicio', { mensagem_id: 'ack', autor: 'sora', agente_id: soraId }));
    e = aplicarEvento(e, ev('mensagem.fim', { mensagem_id: 'ack' }));
    e = aplicarEvento(e, ev('cadeia.criada', { cadeia_id: 'c1', versao: 1, etapas: [] }));
    expect(gerandoNa(e, conversaId, AGORA + 5_000)).toBe(true);
    e = aplicarEvento(e, ev('cadeia.atualizada', { cadeia_id: 'c1', status: 'concluida' }));
    expect(gerandoNa(e, conversaId, AGORA + 5_000)).toBe(false);
  });
});

describe('resposta direta: espera pela resposta', () => {
  it('sem resposta do agente, a espera acaba sozinha e o histórico já carregado não a reabre', () => {
    let e = aplicarEvento(estado(), ev('roteamento', { modo: 'direto' }));
    expect(gerandoNa(e, conversaId, AGORA + 10 * 60_000)).toBe(false);
    e = aplicarEvento({ ...estado(), historicos: { [conversaId]: { carregando: false, carregado: true, anteriores: false, ultimo: AGORA + 1e6 } } }, ev('roteamento', { modo: 'direto' }));
    expect(gerandoNa(e, conversaId, AGORA + 5_000)).toBe(false);
  });

  it('erro encerra a espera', () => {
    let e = aplicarEvento(estado(), ev('roteamento', { modo: 'direto' }));
    e = aplicarEvento(e, ev('erro', { mensagem: 'Falhou' }));
    expect(gerandoNa(e, conversaId, AGORA + 5_000)).toBe(false);
  });
});
