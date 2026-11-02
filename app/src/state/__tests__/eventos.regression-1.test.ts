import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const acompanharEventos = vi.hoisted(() => vi.fn());
const get = vi.hoisted(() => vi.fn());

vi.mock('../../api/eventos', async (importar) => ({
  ...(await importar<typeof import('../../api/eventos')>()),
  acompanharEventos,
}));
vi.mock('../../api/cliente', async (importar) => ({
  ...(await importar<typeof import('../../api/cliente')>()),
  api: { get, post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import { ErroApi } from '../../api/cliente';
import {
  _reiniciarProjetosParaTestes,
  acompanharConversa,
  iniciarProjetos,
  lerEstado,
} from '../projetos';

type Opcoes = Parameters<typeof import('../../api/eventos').acompanharEventos>[1];

beforeEach(() => {
  acompanharEventos.mockReset();
  acompanharEventos.mockImplementation(() => new Promise<void>(() => {}));
  get.mockReset();
  get.mockImplementation((caminho: string) => Promise.resolve(caminho === '/v1/conversas' ? [] : []));
});

afterEach(() => _reiniciarProjetosParaTestes());

describe('regressões dos streams SSE', () => {
  // Regression: ISSUE-001 — um stream reconectado apagava o aviso de 429 do outro
  // Found by /qa on 2026-11-02
  // Report: .gstack/qa-reports/qa-report-sora-local-2026-11-02.md
  it('mantém o aviso até todos os canais com erro reconectarem', async () => {
    await iniciarProjetos();
    acompanharConversa('conversa-1');
    const geral = acompanharEventos.mock.calls[0]?.[1] as Opcoes;
    const conversa = acompanharEventos.mock.calls[1]?.[1] as Opcoes;

    conversa.aoErro?.(new ErroApi(429, 'Muitas tentativas.'));
    expect(lerEstado().erroEventos).toContain('muitas abas ou recargas');

    geral.aoConectar?.();
    expect(lerEstado().erroEventos).toContain('muitas abas ou recargas');

    conversa.aoConectar?.();
    expect(lerEstado().erroEventos).toBeUndefined();
  });

  // Regression: ISSUE-002 — a finalização tardia do stream antigo removia o controlador novo
  // Found by /qa on 2026-11-02
  // Report: .gstack/qa-reports/qa-report-sora-local-2026-11-02.md
  it('não remove o controlador novo quando o stream antigo termina depois', async () => {
    const resolvers: (() => void)[] = [];
    acompanharEventos.mockImplementation(() => new Promise<void>(resolver => resolvers.push(resolver)));

    acompanharConversa('conversa-a');
    acompanharConversa('conversa-b');
    acompanharConversa('conversa-a');
    expect(acompanharEventos).toHaveBeenCalledTimes(3);

    resolvers[0]?.();
    await Promise.resolve();
    acompanharConversa('conversa-a');
    expect(acompanharEventos).toHaveBeenCalledTimes(3);
  });
});
