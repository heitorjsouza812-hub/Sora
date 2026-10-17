import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../sessao', () => ({ recarregarSessao: vi.fn(async () => {}) }));

const provedorOpenAI = { id: 'prov-1', tipo: 'openai', base_url: null, chave_final: '1234', teto_mensal_usd: '20.00', gasto_mes_usd: '3.50' };
const modeloAtivo = { id: 'mod-1', provedor_id: 'prov-1', modelo: 'gpt-5', nivel: 'N2', capacidades: ['texto'], contexto: 128000, preco_entrada: '1', preco_saida: '2', velocidade_tps: 50, ativo: true };

function resposta(corpo: unknown, status = 200) {
  return new Response(status === 204 ? null : JSON.stringify(corpo), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('state/modelos', () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('exibe nome amigável sem alterar o identificador técnico do modelo', async () => {
    const store = await import('../modelos');
    const tecnico = { modelo: 'openai/lince-grande' };

    expect(store.nomeAmigavelDoModelo(tecnico)).toBe('lince-grande');
    expect(tecnico.modelo).toBe('openai/lince-grande');
    expect(store.nomeAmigavelDoModelo({ ...tecnico, nome_exibicao: 'Lince Grande' })).toBe('Lince Grande');
  });

  it('migra sora.modelos.v1 removendo chaves e estado antigo dos provedores', async () => {
    localStorage.setItem('sora.modelos.v1', JSON.stringify({
      versao: 1,
      provedores: { openai: { chave: 'sk-segredo-total', status: 'conectado' } },
      padraoSora: { provedor: 'openai', modelo: 'gpt-5' },
      modelosPorAgente: {},
    }));

    const store = await import('../modelos');
    const salvo = localStorage.getItem('sora.modelos.v1') ?? '';

    expect(store.lerModelos().padraoSora).toEqual({ provedor: 'openai', modelo: 'gpt-5' });
    expect(JSON.parse(salvo)).toEqual({ versao: 2, padraoSora: { provedor: 'openai', modelo: 'gpt-5' }, padraoNovosAgentes: null, modelosPorAgente: {} });
    expect(salvo).not.toContain('segredo');
    expect(salvo).not.toContain('provedores');
    expect(salvo).not.toContain('status');
  });

  it('carrega provedores, modelos e prioridade do backend e oferece só ativos', async () => {
    const inativo = { ...modeloAtivo, id: 'mod-2', modelo: 'gpt-antigo', ativo: false };
    vi.stubGlobal('fetch', vi.fn(async (entrada: RequestInfo | URL) => {
      const url = String(entrada);
      if (url.endsWith('/v1/provedores')) return resposta([provedorOpenAI]);
      if (url.endsWith('/v1/modelos')) return resposta([modeloAtivo, inativo]);
      if (url.endsWith('/v1/eu')) return resposta({ prioridade: 'qualidade' });
      throw new Error(`URL inesperada: ${url}`);
    }));
    const store = await import('../modelos');

    await store.carregarModelos();

    expect(store.lerModelos()).toMatchObject({ prioridade: 'qualidade', carregado: true, carregando: false });
    expect(store.lerModelos().provedores.openai.conexao).toMatchObject({ chave_final: '1234', gasto_mes_usd: '3.50' });
    expect(store.modelosAtivos().map(x => x.modelo.modelo)).toEqual(['gpt-5']);
  });

  it('conecta cartão compatível com o tipo e base_url definidos pela regra 5', async () => {
    const fetchMock = vi.fn(async (entrada: RequestInfo | URL, init?: RequestInit) => {
      const url = String(entrada);
      if (init?.method === 'POST' && url.endsWith('/v1/provedores')) return resposta({ provedor: provedorOpenAI, modelos: [modeloAtivo] }, 201);
      if (url.endsWith('/v1/provedores')) return resposta([]);
      if (url.endsWith('/v1/modelos')) return resposta([]);
      if (url.endsWith('/v1/eu')) return resposta({ prioridade: 'custo' });
      throw new Error(`URL inesperada: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    const store = await import('../modelos');

    await store.conectarProvedor('xai', { chave: 'xai-segredo' });

    const chamada = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(JSON.parse(String(chamada?.[1]?.body))).toEqual({ tipo: 'compativel_openai', chave: 'xai-segredo', base_url: 'https://api.x.ai/v1' });
    expect(localStorage.getItem('sora.modelos.v1') ?? '').not.toContain('xai-segredo');
  });

  it('edita nível/ativo e prioridade pelas rotas reais', async () => {
    const fetchMock = vi.fn(async (entrada: RequestInfo | URL, init?: RequestInit) => {
      const url = String(entrada);
      if (url.endsWith('/v1/modelos/mod-1')) return resposta({ ...modeloAtivo, nivel: 'N3', ativo: false });
      if (url.endsWith('/v1/preferencias')) return resposta(undefined, 204);
      if (url.endsWith('/v1/eu')) return resposta({ prioridade: 'velocidade' });
      throw new Error(`URL inesperada: ${url} ${init?.method}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    const store = await import('../modelos');

    await store.atualizarModelo('mod-1', { nivel: 'N3', ativo: false });
    await store.definirPrioridade('velocidade');

    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/v1/modelos/mod-1'), expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ nivel: 'N3', ativo: false }) }));
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/v1/preferencias'), expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ prioridade: 'velocidade' }) }));
    expect(store.lerModelos().prioridade).toBe('velocidade');
  });
});
