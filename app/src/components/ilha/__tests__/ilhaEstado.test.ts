import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type Store = typeof import('../../../state/projetos');
type Ilha = typeof import('../ilhaEstado');

const AGORA = 1_700_000_000_000;
let store: Store;
let ilha: Ilha;

beforeEach(async () => {
  localStorage.clear();
  vi.useFakeTimers();
  vi.setSystemTime(AGORA);
  vi.resetModules();
  store = await import('../../../state/projetos');
  ilha = await import('../ilhaEstado');
});

afterEach(() => {
  vi.useRealTimers();
});

describe('visaoIlha', () => {
  it('usa o projeto ativo no modo automático e respeita a escolha manual', () => {
    const primeiro = store.criarProjeto('Crie uma campanha para minha cafeteria', AGORA);
    const escolhido = store.criarProjeto('Pesquise o mercado de cafeterias', AGORA + 100);
    store.abrirProjeto(primeiro.id);

    const automatica = ilha.visaoIlha(store.lerEstado(), AGORA + 200, null);
    const manual = ilha.visaoIlha(store.lerEstado(), AGORA + 200, escolhido.id);

    expect(automatica).toMatchObject({ automatico: true, projeto: { id: primeiro.id } });
    expect(manual).toMatchObject({ automatico: false, projeto: { id: escolhido.id } });
  });

  it('volta ao modo automático quando o projeto escolhido foi apagado', () => {
    const automatico = store.criarProjeto('Crie uma campanha para minha cafeteria', AGORA);
    const apagado = store.criarProjeto('Crie um site para uma cafeteria', AGORA + 100);
    store.abrirProjeto(automatico.id);
    store.removerProjeto(apagado.id);

    const visao = ilha.visaoIlha(store.lerEstado(), AGORA + 200, apagado.id);

    expect(visao).toMatchObject({ automatico: true, projeto: { id: automatico.id } });
  });

  it('ordena projetos rodando antes dos projetos parados', () => {
    const rodando = store.criarProjeto('Crie uma campanha para minha cafeteria', AGORA);
    const aprovado = store.criarProjeto('Crie um site para minha cafeteria', AGORA + 100);
    store.aprovarProjeto(aprovado.id, AGORA + 200);

    const visao = ilha.visaoIlha(store.lerEstado(), AGORA + 300, null);

    expect(visao.projetos.map((projeto) => projeto.id)).toEqual([rodando.id, aprovado.id]);
    expect(visao.projetos.map((projeto) => projeto.rodando)).toEqual([true, false]);
  });

  it('expõe agentes, ticker e alerta de revisão quando o projeto fica pronto', () => {
    const projeto = store.criarProjeto('Crie uma campanha para lançar minha cafeteria', AGORA);
    const visao = ilha.visaoIlha(store.lerEstado(), projeto.marcos.fim, projeto.id);

    expect(visao.projeto).toMatchObject({ id: projeto.id, fase: 'pronto', progresso: 100 });
    expect(visao.agentes).toHaveLength(projeto.agenteIds.length);
    expect(visao.agentes.every((agente) => agente.status === 'concluido' && agente.orb === 'done' && agente.progresso === 100)).toBe(true);
    expect(visao.ticker).toHaveLength(6);
    expect(visao.ticker.every((passo, indice, passos) => indice === 0 || passos[indice - 1]!.inicio <= passo.inicio)).toBe(true);
    expect(visao.ticker.at(-1)?.status).toBe('concluido');
    expect(visao).toMatchObject({
      trabalhando: 0,
      alerta: {
        tipo: 'revisar',
        projetoId: projeto.id,
        titulo: projeto.titulo,
      },
    });
    expect(visao.alerta?.entregas).toHaveLength(projeto.agenteIds.length);
  });
});

describe('preferências da Ilha', () => {
  it('persiste as preferências e as recarrega em um novo módulo', async () => {
    const preferencias = { visivel: false, som: false, esconderOciosa: true, projetoId: 'proj-escolhido' };

    ilha.definirIlhaPrefs(preferencias);

    expect(JSON.parse(localStorage.getItem('sora.ilha.v1') ?? '{}')).toEqual(preferencias);

    vi.resetModules();
    const recarregada = await import('../ilhaEstado');
    expect(recarregada.lerIlhaPrefs()).toEqual(preferencias);
  });
});
