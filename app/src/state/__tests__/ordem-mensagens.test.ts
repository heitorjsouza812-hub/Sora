import { describe, expect, it } from 'vitest';
import { aplicarEvento, registrarEnvioDoUsuario } from '../aplicarEvento';
import { mensagensDa, type EstadoProjetos } from '../projetos';

const base = (): EstadoProjetos => ({
  versao: 2, sora: { nome: 'Sora', cor: '#E2ECFF' }, agentes: {}, projetos: [], projetoAtivoId: null,
  execucoes: [], mensagens: [], pluginsConectados: [], carregando: false,
} as unknown as EstadoProjetos);

const inicio = (id: string, recebidoEm: number) => ({ tipo: 'mensagem.inicio', dados: { mensagem_id: id, conversa_id: 'c1', autor: 'sora' }, recebidoEm }) as never;

describe('ordem das mensagens', () => {
  it('a resposta da Sora que chega por SSE ANTES do POST voltar fica depois do balão do usuário', () => {
    const enviadoEm = 1_000;
    // a Sora responde (SSE) em t=3000, mas o POST só devolve o id em t=5000
    let e = aplicarEvento(base(), inicio('m-sora', 3_000));
    e = registrarEnvioDoUsuario(e, { id: 'm-user', conversaId: 'c1', texto: 'guarde na memória', enviadoEm });
    expect(mensagensDa(e, 'c1', 5_000).map(m => m.id)).toEqual(['m-user', 'm-sora']);
  });

  it('se o eco do usuário já chegou, só corrige o carimbo e não duplica', () => {
    let e = aplicarEvento(base(), { tipo: 'mensagem.inicio', dados: { mensagem_id: 'm-user', conversa_id: 'c1', autor: 'usuario' }, recebidoEm: 4_000 } as never);
    e = aplicarEvento(e, inicio('m-sora', 3_500));
    e = registrarEnvioDoUsuario(e, { id: 'm-user', conversaId: 'c1', texto: 'oi', enviadoEm: 1_000 });
    const ids = mensagensDa(e, 'c1', 5_000).map(m => m.id);
    expect(ids).toEqual(['m-user', 'm-sora']);
    expect(e.mensagens.filter(m => m.id === 'm-user')).toHaveLength(1);
  });
});
