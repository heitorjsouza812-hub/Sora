import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { EstadoProjetos } from '../../../state/projetos';

const AGORA = 1_700_000_000_000;

function estadoReal(): EstadoProjetos {
  const projeto = {
    id: 'projeto-1', tipo: 'projeto' as const, titulo: 'Campanha da cafeteria', pedido: 'Crie uma campanha', modelo: '', assunto: 'Cafeteria', resposta: '', criadoEm: AGORA,
    tarefas: [
      { id: 'e1', titulo: 'Pesquisa', ordem: 1, dependeDe: [], agenteId: 'a1', status: 'concluido' as const, progresso: 100 },
      { id: 'e2', titulo: 'Criação', ordem: 2, dependeDe: ['e1'], agenteId: 'a2', status: 'trabalhando' as const, progresso: 50 },
      { id: 'e3', titulo: 'Textos', ordem: 3, dependeDe: ['e2'], agenteId: 'a3', status: 'aguardando' as const, progresso: 0 },
    ],
    agenteIds: ['a1', 'a2', 'a3'], entregas: { a1: { id: 'd1', agenteId: 'a1', versao: 1, tipo: 'links' as const, titulo: 'Pesquisa', resumo: '4 referências' } },
    marcos: { plano: AGORA, nascimentos: [], trabalho: AGORA, fim: AGORA }, aprovadaVersao: null, versao: 1, cadeiaId: 'c1', cadeiaStatus: 'executando' as const,
  };
  return {
    versao: 2, sora: { nome: 'Sora', cor: '#E2ECFF' }, projetoAtivoId: projeto.id, projetos: [projeto], pluginsConectados: [], carregando: false, mensagens: [],
    agentes: {
      a1: { id: 'a1', projetoId: projeto.id, nome: 'Atlas', funcao: 'Pesquisa', cor: '#56A8FF', tipoMovimento: 'vibracao', ferramentas: [], status: 'aguardando', verbo: 'Pesquisando', espera: 'Aguardando', instrucoes: '', avulso: false, criadoEm: AGORA },
      a2: { id: 'a2', projetoId: projeto.id, nome: 'Luna', funcao: 'Visual', cor: '#AC80FF', tipoMovimento: 'espiral', ferramentas: [], status: 'aguardando', verbo: 'Criando', espera: 'Aguardando', instrucoes: '', avulso: false, criadoEm: AGORA },
      a3: { id: 'a3', projetoId: projeto.id, nome: 'Nina', funcao: 'Textos', cor: '#46E8A8', tipoMovimento: 'ondas', ferramentas: [], status: 'aguardando', verbo: 'Escrevendo', espera: 'Aguardando', instrucoes: '', avulso: false, criadoEm: AGORA },
    },
    execucoes: [
      { id: 'e1', agenteId: 'a1', projetoId: projeto.id, tarefaId: 'e1', inicio: AGORA, status: 'concluida', progresso: 100, roteiro: [{ id: 'p1', agenteId: 'a1', tipo: 'entrega', texto: 'Entregou', status: 'concluido', inicio: AGORA, fim: AGORA + 1 }] },
      { id: 'e2', agenteId: 'a2', projetoId: projeto.id, tarefaId: 'e2', inicio: AGORA + 2, status: 'executando', progresso: 50, roteiro: [{ id: 'p2', agenteId: 'a2', tipo: 'ferramenta', texto: 'Criando', ferramenta: 'gerar_imagem', status: 'executando', inicio: AGORA + 2 }] },
      { id: 'e3', agenteId: 'a3', projetoId: projeto.id, tarefaId: 'e3', inicio: AGORA + 3, status: 'pendente', progresso: 0, roteiro: [] },
    ],
  };
}

let ilha: typeof import('../ilhaEstado');
beforeEach(async () => { localStorage.clear(); vi.resetModules(); ilha = await import('../ilhaEstado'); });

describe('visaoIlha com estado do backend', () => {
  it('expõe agentes, progresso e ticker recebidos do SSE', () => {
    const visao = ilha.visaoIlha(estadoReal(), AGORA + 10, null);
    expect(visao.projeto).toMatchObject({ id: 'projeto-1', fase: 'coordenando', progresso: 50 });
    expect(visao.agentes.map(a => a.status)).toEqual(['concluido', 'trabalhando', 'aguardando']);
    expect(visao.ticker.map(p => p.id)).toEqual(['p1', 'p2']);
    expect(visao.trabalhando).toBe(1);
  });

  it('mostra alerta somente depois do evento de cadeia concluída', () => {
    const e = estadoReal();
    expect(ilha.visaoIlha(e, AGORA, null).alerta).toBeNull();
    e.projetos[0]!.cadeiaStatus = 'concluida';
    const visao = ilha.visaoIlha(e, AGORA, null);
    expect(visao.alerta).toMatchObject({ tipo: 'revisar', projetoId: 'projeto-1', entregas: ['Pesquisa · 4 referências'] });
  });

  it('filtra agentes sem inventar transições por tempo', () => {
    const agentes = ilha.visaoIlha(estadoReal(), AGORA + 999_999, null).agentes;
    expect(ilha.filtrarAgentes(agentes, { filtro: 'trabalhando', ocultos: [] }).map(a => a.id)).toEqual(['a2']);
    expect(ilha.filtrarAgentes(agentes, { filtro: 'concluidos', ocultos: [] }).map(a => a.id)).toEqual(['a1']);
  });
});

describe('preferências da Ilha', () => {
  it('alterna agente oculto e persiste a preferência', () => {
    ilha.alternarAgenteOculto('a1'); ilha.alternarAgenteOculto('a1'); ilha.alternarAgenteOculto('a2');
    expect(ilha.lerIlhaPrefs().ocultos).toEqual(['a2']);
    expect(JSON.parse(localStorage.getItem('sora.ilha.v1') ?? '{}')).toMatchObject({ ocultos: ['a2'] });
  });

  it('migra preferências antigas com os padrões atuais', async () => {
    const antigas = { visivel: false, som: false, esconderOciosa: true, projetoId: 'projeto-antigo' };
    localStorage.setItem('sora.ilha.v1', JSON.stringify(antigas)); vi.resetModules(); const migrada = await import('../ilhaEstado');
    expect(migrada.lerIlhaPrefs()).toEqual({ ...antigas, filtro: 'todos', ocultos: [], ilhaNoApp: false });
  });
});
