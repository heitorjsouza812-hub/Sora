import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type Store = typeof import('../projetos');

const AGORA = 1_700_000_000_000;
let store: Store;

beforeEach(async () => {
  localStorage.clear();
  vi.useFakeTimers();
  vi.setSystemTime(AGORA);
  vi.resetModules();
  store = await import('../projetos');
});

afterEach(() => {
  vi.useRealTimers();
});

describe('state/projetos', () => {
  it('cria projeto com equipe e deriva progresso e fases pelo agora informado', () => {
    const projeto = store.criarProjeto('Crie uma campanha para minha cafeteria', AGORA);
    const estado = store.lerEstado();

    expect(estado.projetos[0]).toMatchObject({ id: projeto.id, modelo: 'campanha' });
    expect(projeto.agenteIds).toHaveLength(3);
    expect(estado.execucoes).toHaveLength(projeto.tarefas.length);
    expect(store.estadoProjeto(estado, projeto, projeto.marcos.plano - 1).fase).toBe('pensando');
    expect(store.estadoProjeto(estado, projeto, projeto.marcos.plano).fase).toBe('planejando');
    expect(store.estadoProjeto(estado, projeto, projeto.marcos.trabalho).fase).toBe('coordenando');
    expect(store.estadoProjeto(estado, projeto, projeto.marcos.fim)).toMatchObject({ fase: 'pronto', progresso: 100 });
  });

  it('remove projeto junto com agentes, execuções e mensagens da equipe', () => {
    const projeto = store.criarProjeto('Crie uma campanha para minha cafeteria', AGORA);
    const desfazer = store.removerProjeto(projeto.id);
    const estado = store.lerEstado();

    expect(estado.projetos).toHaveLength(0);
    expect(estado.execucoes).toHaveLength(0);
    expect(estado.mensagens).toHaveLength(0);
    expect(projeto.agenteIds.every((id) => estado.agentes[id] === undefined)).toBe(true);

    desfazer();
    expect(store.lerEstado().projetos[0]?.id).toBe(projeto.id);
  });

  it('mantém agentes como avulsos ao remover projeto com manterAgentes', () => {
    const projeto = store.criarProjeto('Crie uma campanha para minha cafeteria', AGORA);
    store.removerProjeto(projeto.id, { manterAgentes: true });
    const estado = store.lerEstado();

    expect(estado.projetos).toHaveLength(0);
    expect(estado.execucoes).toHaveLength(0);
    for (const id of projeto.agenteIds) {
      expect(estado.agentes[id]).toMatchObject({ avulso: true, projetoId: '', espera: 'Disponível' });
    }
  });

  it('renomeia apenas título não vazio do projeto', () => {
    const projeto = store.criarProjeto('Crie uma campanha para minha cafeteria', AGORA);
    store.renomearProjeto(projeto.id, '  Lançamento da Sora  ');
    expect(store.lerEstado().projetos[0]?.titulo).toBe('Lançamento da Sora');

    store.renomearProjeto(projeto.id, '   ');
    expect(store.lerEstado().projetos[0]?.titulo).toBe('Lançamento da Sora');
  });

  it('salva, atualiza e remove agente avulso', () => {
    const agente = store.salvarAgente({
      nome: 'Lia', funcao: 'Textos', cor: '#FF6FAE', tipoMovimento: 'ondas', ferramentas: ['Notion'], instrucoes: 'Escreva em PT-BR.',
    });
    expect(store.lerEstado().agentes[agente.id]).toMatchObject({ nome: 'Lia', avulso: true, verbo: 'Escrevendo' });

    store.atualizarAgente(agente.id, { funcao: 'Código', ferramentas: ['GitHub'] });
    expect(store.lerEstado().agentes[agente.id]).toMatchObject({ funcao: 'Código', verbo: 'Programando', ferramentas: ['GitHub'] });

    store.removerAgente(agente.id);
    expect(store.lerEstado().agentes[agente.id]).toBeUndefined();
  });

  it('persiste alterações no localStorage e as recarrega em novo módulo', async () => {
    const projeto = store.criarProjeto('Crie uma campanha para minha cafeteria', AGORA);
    store.renomearProjeto(projeto.id, 'Campanha persistida');

    const salvo = JSON.parse(localStorage.getItem('sora.projetos.v1') ?? '{}');
    expect(salvo.projetos[0]).toMatchObject({ id: projeto.id, titulo: 'Campanha persistida' });

    vi.resetModules();
    const recarregado = await import('../projetos');
    expect(recarregado.lerEstado().projetos[0]).toMatchObject({ id: projeto.id, titulo: 'Campanha persistida' });
  });
  it('modo agente independente: cria UM agente avulso (fora de equipes) que já começa a trabalhar', () => {
    const ag = store.criarAgenteIndependente('Pesquise tendências de café gelado no Instagram', AGORA);
    const estado = store.lerEstado();

    expect(estado.projetos).toHaveLength(0);
    expect(estado.agentes[ag.id]).toMatchObject({ avulso: true, projetoId: '', funcao: 'Pesquisa e referências' });
    expect(estado.execucoes.filter(x => x.agenteId === ag.id)).toHaveLength(1);
    expect(estado.mensagens.filter(m => m.conversaId === ag.id).map(m => m.autor)).toEqual(['usuario', ag.id]);
    const x = estado.execucoes[0];
    expect(store.estadoAgente(estado, ag.id, x.inicio + 1).status).toBe('trabalhando');
  });});
