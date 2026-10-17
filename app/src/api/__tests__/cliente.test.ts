import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Ponte do desktop simulada: `desktop.ativo` liga/desliga o modo Tauri por teste.
const desktop = vi.hoisted(() => ({ ativo: false, cofre: null as string | null }));
vi.mock('../../desktop/ponte', () => ({
  get noDesktop() { return desktop.ativo; },
  cofreLer: vi.fn(async () => desktop.cofre),
  cofreGravar: vi.fn(async (t: string) => { desktop.cofre = t; }),
  cofreApagar: vi.fn(async () => { desktop.cofre = null; }),
}));

import {
  _reiniciarClienteParaTestes, aoSessaoEncerrada, api, definirTokenAcesso, ErroApi, guardarTokens,
  MSG_SEM_REDE, renovarSessao, temTokenAcesso,
} from '../cliente';

const json = (status: number, corpo: unknown, headers: Record<string, string> = {}) =>
  new Response(corpo === undefined ? null : JSON.stringify(corpo), { status, headers: { 'Content-Type': 'application/json', ...headers } });

type Chamada = { url: string; init: RequestInit };
let chamadas: Chamada[];
let respostas: ((c: Chamada) => Response | Promise<Response>)[];

const cabecalhos = (c: Chamada) => c.init.headers as Record<string, string>;

beforeEach(() => {
  _reiniciarClienteParaTestes();
  desktop.ativo = false;
  desktop.cofre = null;
  chamadas = [];
  respostas = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    const c = { url, init };
    chamadas.push(c);
    const r = respostas.shift();
    if (!r) throw new Error(`fetch inesperado: ${url}`);
    return r(c);
  }));
});

afterEach(() => { vi.unstubAllGlobals(); });

describe('api', () => {
  it('manda o token de acesso, JSON e devolve o corpo', async () => {
    definirTokenAcesso('acesso-1');
    respostas.push(() => json(200, { ok: true }));
    const r = await api.post<{ ok: boolean }>('/v1/provedores', { tipo: 'openai' });
    expect(r).toEqual({ ok: true });
    expect(chamadas[0].url).toBe('/v1/provedores');
    expect(chamadas[0].init.method).toBe('POST');
    expect(chamadas[0].init.body).toBe(JSON.stringify({ tipo: 'openai' }));
    expect(cabecalhos(chamadas[0]).Authorization).toBe('Bearer acesso-1');
    expect(cabecalhos(chamadas[0])['Content-Type']).toBe('application/json');
    expect(cabecalhos(chamadas[0])['X-Sora-Cliente']).toBeUndefined();
  });

  it('204 devolve undefined', async () => {
    respostas.push(() => new Response(null, { status: 204 }));
    await expect(api.delete('/v1/provedores/1')).resolves.toBeUndefined();
  });

  it('erro vira ErroApi com a mensagem PT-BR do backend', async () => {
    respostas.push(() => json(409, { detail: 'Você já tem esse provedor conectado.' }));
    const e = await api.post('/v1/provedores', {}).catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ErroApi);
    expect(e).toMatchObject({ status: 409, mensagem: 'Você já tem esse provedor conectado.' });
  });

  it('422 de validação (detail em lista) vira mensagem genérica PT-BR', async () => {
    respostas.push(() => json(422, { detail: [{ loc: ['body', 'chave'], msg: 'Field required', type: 'missing' }] }));
    const e = await api.post('/v1/provedores', {}).catch((x: unknown) => x) as ErroApi;
    expect(e.status).toBe(422);
    expect(e.mensagem).toBe('Confira os campos e tente de novo.');
    expect(Array.isArray(e.detalhe)).toBe(true);
  });

  it('429 lê Retry-After', async () => {
    respostas.push(() => json(429, { detail: 'Muitas tentativas.' }, { 'Retry-After': '30' }));
    const e = await api.get('/v1/modelos').catch((x: unknown) => x) as ErroApi;
    expect(e).toMatchObject({ status: 429, mensagem: 'Muitas tentativas.', tentarEmSegundos: 30 });
  });

  it('rede fora → status 0 e mensagem de servidor fora', async () => {
    respostas.push(() => { throw new TypeError('Failed to fetch'); });
    const e = await api.get('/v1/eu').catch((x: unknown) => x) as ErroApi;
    expect(e).toMatchObject({ status: 0, mensagem: MSG_SEM_REDE });
  });
});

describe('renovação no 401', () => {
  it('renova uma vez e repete o pedido com o token novo', async () => {
    definirTokenAcesso('velho');
    respostas.push(() => json(401, { detail: 'Sessão expirada.' }));
    respostas.push(() => json(200, { token_acesso: 'novo' }));
    respostas.push(() => json(200, { nome: 'Ana' }));
    await expect(api.get('/v1/eu')).resolves.toEqual({ nome: 'Ana' });
    expect(chamadas.map(c => c.url)).toEqual(['/v1/eu', '/v1/auth/renovar', '/v1/eu']);
    expect(chamadas[1].init.credentials).toBe('include');
    expect(chamadas[1].init.body).toBeUndefined();
    expect(cabecalhos(chamadas[2]).Authorization).toBe('Bearer novo');
  });

  it('vários 401 ao mesmo tempo dividem uma única renovação', async () => {
    definirTokenAcesso('velho');
    respostas.push(() => json(401, {}), () => json(401, {}));
    let liberar!: () => void;
    respostas.push(() => new Promise<Response>(ok => { liberar = () => ok(json(200, { token_acesso: 'novo' })); }));
    respostas.push(() => json(200, 'a'), () => json(200, 'b'));
    const p = Promise.all([api.get('/v1/a'), api.get('/v1/b')]);
    await vi.waitFor(() => expect(chamadas.filter(c => c.url === '/v1/auth/renovar')).toHaveLength(1));
    liberar();
    await expect(p).resolves.toEqual(['a', 'b']);
    expect(chamadas.filter(c => c.url === '/v1/auth/renovar')).toHaveLength(1);
  });

  it('renovação recusada encerra a sessão e avisa quem ouve', async () => {
    definirTokenAcesso('velho');
    const encerrada = vi.fn();
    const parar = aoSessaoEncerrada(encerrada);
    respostas.push(() => json(401, { detail: 'Sessão expirada.' }));
    respostas.push(() => json(401, { detail: 'Faça login de novo.' }));
    const e = await api.get('/v1/eu').catch((x: unknown) => x) as ErroApi;
    expect(e.status).toBe(401);
    expect(encerrada).toHaveBeenCalledTimes(1);
    expect(temTokenAcesso()).toBe(false);
    parar();
  });

  it('erro de rede ao renovar encerra a sessão e preserva a mensagem de rede', async () => {
    definirTokenAcesso('velho');
    const encerrada = vi.fn();
    const parar = aoSessaoEncerrada(encerrada);
    respostas.push(() => json(401, { detail: 'Sessão expirada.' }));
    respostas.push(() => { throw new TypeError('Failed to fetch'); });
    await expect(api.get('/v1/eu')).rejects.toMatchObject({ status: 0, mensagem: MSG_SEM_REDE });
    expect(encerrada).toHaveBeenCalledTimes(1);
    expect(temTokenAcesso()).toBe(false);
    parar();
  });

  it('erro do servidor ao renovar encerra a sessão e preserva a mensagem do backend', async () => {
    definirTokenAcesso('velho');
    const encerrada = vi.fn();
    const parar = aoSessaoEncerrada(encerrada);
    respostas.push(() => json(401, { detail: 'Sessão expirada.' }));
    respostas.push(() => json(503, { detail: 'Renovação indisponível.' }));
    await expect(api.get('/v1/eu')).rejects.toMatchObject({ status: 503, mensagem: 'Renovação indisponível.' });
    expect(encerrada).toHaveBeenCalledTimes(1);
    expect(temTokenAcesso()).toBe(false);
    parar();
  });

  it('não repete mais de uma vez se o pedido repetido também der 401', async () => {
    const encerrada = vi.fn();
    const parar = aoSessaoEncerrada(encerrada);
    respostas.push(() => json(401, {}), () => json(200, { token_acesso: 'novo' }), () => json(401, {}));
    await expect(api.get('/v1/eu')).rejects.toMatchObject({ status: 401 });
    expect(chamadas).toHaveLength(3);
    expect(encerrada).toHaveBeenCalledTimes(1);
    parar();
  });

  it('semAuth não manda token nem tenta renovar', async () => {
    definirTokenAcesso('x');
    respostas.push(() => json(401, { detail: 'E-mail ou senha incorretos.' }));
    await expect(api.post('/v1/auth/entrar', {}, { semAuth: true })).rejects.toMatchObject({ mensagem: 'E-mail ou senha incorretos.' });
    expect(chamadas).toHaveLength(1);
    expect(cabecalhos(chamadas[0]).Authorization).toBeUndefined();
  });
});

describe('desktop (Tauri)', () => {
  beforeEach(() => { desktop.ativo = true; });

  it('manda X-Sora-Cliente: desktop', async () => {
    respostas.push(() => json(200, {}));
    await api.get('/v1/modelos');
    expect(cabecalhos(chamadas[0])['X-Sora-Cliente']).toBe('desktop');
  });

  it('renova com o token do cofre no corpo e grava o novo no cofre', async () => {
    desktop.cofre = 'renov-1';
    respostas.push(() => json(200, { token_acesso: 'a2', token_renovacao: 'renov-2' }));
    await expect(renovarSessao()).resolves.toBe(true);
    expect(chamadas[0].init.body).toBe(JSON.stringify({ token_renovacao: 'renov-1' }));
    expect(cabecalhos(chamadas[0])['X-Sora-Cliente']).toBe('desktop');
    expect(desktop.cofre).toBe('renov-2');
    expect(temTokenAcesso()).toBe(true);
  });

  it('cofre vazio: não chama o servidor', async () => {
    await expect(renovarSessao()).resolves.toBe(false);
    expect(chamadas).toHaveLength(0);
  });

  it('renovação recusada apaga o cofre', async () => {
    desktop.cofre = 'renov-velho';
    respostas.push(() => json(401, {}));
    await expect(renovarSessao()).resolves.toBe(false);
    expect(desktop.cofre).toBeNull();
  });

  it('guardarTokens grava a renovação no cofre e nunca no localStorage', async () => {
    await guardarTokens({ token_acesso: 'a', token_renovacao: 'r' });
    expect(desktop.cofre).toBe('r');
    expect(JSON.stringify({ ...localStorage })).not.toContain('"r"');
  });
});
