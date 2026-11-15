// C3 (Vela-3): o app de desktop como ponte entre o servidor e o PC. O Rust é simulado; o que se
// testa aqui é o laço: sessão → long-poll → executar → resultado, Parar e outra sessão assumindo.
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const f = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  buscar: vi.fn(),
  ouvintes: {} as Record<string, (p: unknown) => void>,
  executar: vi.fn(),
  conta: vi.fn(),
  autorizar: vi.fn(),
  sair: vi.fn(),
  parar: vi.fn(),
}));

vi.mock('../../api/cliente', async (importar) => ({
  ...(await importar<typeof import('../../api/cliente')>()),
  api: f.api,
  buscarAutenticado: f.buscar,
}));
vi.mock('../ponte', () => ({
  cofreLer: vi.fn(async () => 'credencial-desktop'),
  noDesktop: true,
  janelaAtual: 'main',
  pcConta: f.conta,
  pcAutorizar: f.autorizar,
  pcEstado: vi.fn(async () => null),
  pcExecutar: f.executar,
  pcParar: f.parar,
  pcSair: f.sair,
  aoPcParar: (cb: (id: string) => void) => { f.ouvintes['pc-parar'] = p => cb(p as string); return () => {}; },
  aoPcEstado: (cb: (e: unknown) => void) => { f.ouvintes['pc-estado'] = cb; return () => {}; },
}));
vi.mock('../../state/bots', () => ({
  useBots: () => [
    { id: 'b1', nome: 'Atlas', cor: '#56A8FF', funcao: 'Pesquisa', estado: 'livre', ferramentas: ['computador_observar', 'computador_agir'] },
    { id: 'b2', nome: 'Luna', cor: '#AC80FF', funcao: 'Arte', estado: 'livre', ferramentas: [] },
  ],
}));

import { ErroApi } from '../../api/cliente';
import { ComputadorPC } from '../../components/settings/ComputadorPC';
import { _reiniciarPontePcParaTestes, alternarBotNoPc, iniciarPontePc, lerPontePc } from '../computadorPc';

const LOCAL = { conta: 'u1', autorizados: ['b1'], controlando: null, pausado: false, windows: true, atalho_parar: 'Ctrl+Shift+F12' };
const COMANDO = { id: 'c1', agente: { id: 'b1', nome: 'Atlas', cor: '#56A8FF' }, operacao: 'observar', dados: {}, prazo_ms: 25000 };

function resposta(status: number, corpo?: unknown): Response {
  return { status, ok: status < 400, json: async () => corpo } as Response;
}

beforeEach(() => {
  f.sair.mockResolvedValue(undefined);
  f.parar.mockResolvedValue(undefined);
  f.api.post.mockResolvedValue(undefined);
  f.api.put.mockResolvedValue(undefined);
  f.api.delete.mockResolvedValue(undefined);
});

afterEach(() => {
  [...Object.values(f.api), f.buscar, f.executar, f.conta, f.autorizar, f.sair, f.parar].forEach(m => m.mockReset());
  _reiniciarPontePcParaTestes();
});

describe('ponte do controle do PC', () => {
  it('apresenta a sessão, executa o comando no Rust e devolve o resultado uma vez', async () => {
    f.api.post.mockImplementation(async (caminho: string) => caminho === '/v1/computador-pc/sessao'
      ? { sessao_id: 's1', usuario_id: 'u1', autorizados: [], validade_s: 60 }
      : undefined);
    f.api.put.mockResolvedValue({ autorizados: ['b1'] });
    f.conta.mockResolvedValue(LOCAL);
    f.executar.mockResolvedValue({ ok: true, resultado: { largura: 10 } });
    let chamadas = 0;
    f.buscar.mockImplementation(async () => {
      chamadas += 1;
      if (chamadas === 1) return resposta(200, COMANDO);
      if (chamadas === 2) return resposta(204);
      throw new ErroApi(409, 'Outra sessão do app de desktop assumiu.');
    });

    const parar = iniciarPontePc();
    await waitFor(() => expect(lerPontePc().substituida).toBe(true));
    expect(f.api.post).toHaveBeenCalledWith('/v1/computador-pc/sessao', { dispositivo: expect.any(String), autorizados: [], token_renovacao: 'credencial-desktop' }, expect.anything());
    expect(f.conta).toHaveBeenCalledWith('u1');
    expect(f.api.put).toHaveBeenCalledWith('/v1/computador-pc/sessao/s1', { autorizados: ['b1'] }, expect.anything());
    expect(f.buscar.mock.calls[0][0]).toBe('/v1/computador-pc/comandos?sessao_id=s1&espera=20');
    expect(f.executar).toHaveBeenCalledWith(COMANDO);
    expect(f.api.post).toHaveBeenCalledWith('/v1/computador-pc/comandos/c1/resultado', { sessao_id: 's1', ok: true, resultado: { largura: 10 } });
    expect(f.executar).toHaveBeenCalledTimes(1);
    expect(f.sair).toHaveBeenCalled(); // outra sessão assumiu: este PC solta tudo
    parar();
  });

  it('Parar na borda avisa o servidor; desligar a ponte encerra a sessão', async () => {
    f.api.post.mockImplementation(async (caminho: string) => caminho === '/v1/computador-pc/sessao'
      ? { sessao_id: 's2', usuario_id: 'u1', autorizados: [], validade_s: 60 }
      : undefined);
    f.api.delete.mockResolvedValue(undefined);
    f.conta.mockResolvedValue({ ...LOCAL, autorizados: [], token_renovacao: 'credencial-desktop' });
    f.buscar.mockImplementation((_c: string, init: RequestInit) => new Promise((_, rejeitar) => {
      init.signal?.addEventListener('abort', () => rejeitar(new DOMException('abortado', 'AbortError')));
    }));
    const parar = iniciarPontePc();
    await waitFor(() => expect(lerPontePc().conectado).toBe(true));
    f.ouvintes['pc-parar']('b1');
    expect(f.api.post).toHaveBeenCalledWith('/v1/computador-pc/parar', { sessao_id: 's2', agente_id: 'b1' });
    parar();
    expect(f.api.delete).toHaveBeenCalledWith('/v1/computador-pc/sessao/s2');
    expect(f.sair).toHaveBeenCalled();
    expect(lerPontePc().conectado).toBe(false);
  });

  it('ligar um bot grava no Rust e atualiza a sessão no servidor', async () => {
    f.api.post.mockResolvedValue({ sessao_id: 's3', usuario_id: 'u1', autorizados: [], validade_s: 60 });
    f.conta.mockResolvedValue({ ...LOCAL, autorizados: [], token_renovacao: 'credencial-desktop' });
    f.buscar.mockImplementation(() => new Promise(() => {}));
    const parar = iniciarPontePc();
    await waitFor(() => expect(lerPontePc().sessaoId).toBe('s3'));
    f.autorizar.mockResolvedValue({ ...LOCAL, autorizados: ['b2'] });
    await alternarBotNoPc('b2', true);
    expect(f.autorizar).toHaveBeenCalledWith('b2', true);
    expect(f.api.put).toHaveBeenLastCalledWith('/v1/computador-pc/sessao/s3', { autorizados: ['b2'] });
    parar();
  });
});

describe('Configurações → Computador no app de desktop', () => {
  it('lista os bots desligados por padrão, avisa quem não tem a ferramenta e mostra o Parar', async () => {
    f.api.post.mockResolvedValue({ sessao_id: 's4', usuario_id: 'u1', autorizados: [], validade_s: 60 });
    f.conta.mockResolvedValue({ ...LOCAL, autorizados: [], token_renovacao: 'credencial-desktop' });
    f.buscar.mockImplementation(() => new Promise(() => {}));
    f.autorizar.mockResolvedValue({ ...LOCAL, autorizados: ['b1'] });
    const parar = iniciarPontePc();
    render(<ComputadorPC />);
    const atlas = await screen.findByRole('switch', { name: 'Atlas pode usar este computador' });
    expect(atlas).not.toBeChecked();
    expect(screen.getByText(/Luna/).closest('li')?.textContent).toContain('ainda não tem a ferramenta Computador');
    fireEvent.click(atlas);
    await waitFor(() => expect(f.autorizar).toHaveBeenCalledWith('b1', true));
    await waitFor(() => expect(screen.getByRole('switch', { name: 'Atlas pode usar este computador' })).toBeChecked());

    act(() => f.ouvintes['pc-estado']({ ...LOCAL, controlando: { id: 'b1', nome: 'Atlas', cor: '#56A8FF' }, pausado: true }));
    expect(await screen.findByText(/pausou porque você usou o computador/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Parar' }));
    expect(f.parar).toHaveBeenCalled();
    parar();
  });
});
