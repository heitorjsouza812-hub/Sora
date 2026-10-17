import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../desktop/ponte', () => ({
  noDesktop: false,
  cofreLer: vi.fn(async () => null),
  cofreGravar: vi.fn(async () => {}),
  cofreApagar: vi.fn(async () => {}),
}));

import { _reiniciarClienteParaTestes, api } from '../../api/cliente';
import { _reiniciarSessaoParaTestes, apagarConta, cadastrar, entrar, iniciarSessao, lerSessao, sair } from '../sessao';

const json = (status: number, corpo?: unknown) =>
  new Response(corpo === undefined ? null : JSON.stringify(corpo), { status, headers: { 'Content-Type': 'application/json' } });

const ANA = { nome: 'Ana Souza', email: 'ana@exemplo.com', prioridade: 'qualidade', tem_provedor: false };

let rotas: Record<string, (init: RequestInit) => Response>;
let chamadas: { url: string; init: RequestInit }[];

beforeEach(() => {
  _reiniciarClienteParaTestes();
  _reiniciarSessaoParaTestes();
  chamadas = [];
  rotas = {};
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    chamadas.push({ url, init });
    const r = rotas[`${init.method} ${url}`];
    if (!r) throw new Error(`fetch inesperado: ${init.method} ${url}`);
    return r(init);
  }));
});

afterEach(() => { vi.unstubAllGlobals(); });

describe('sessão', () => {
  it('abertura sem cookie de renovação → anônimo', async () => {
    rotas['POST /v1/auth/renovar'] = () => json(401, { detail: 'Sessão inválida.' });
    await iniciarSessao();
    expect(lerSessao().estado).toBe('anonimo');
  });

  it('abertura com cookie válido → logado com GET /v1/eu', async () => {
    rotas['POST /v1/auth/renovar'] = () => json(200, { token_acesso: 'a' });
    rotas['GET /v1/eu'] = () => json(200, ANA);
    await iniciarSessao();
    expect(lerSessao()).toEqual({ estado: 'logado', usuario: ANA });
  });

  it('servidor fora na abertura → anônimo com aviso', async () => {
    rotas['POST /v1/auth/renovar'] = () => { throw new TypeError('rede'); };
    await iniciarSessao();
    expect(lerSessao()).toMatchObject({ estado: 'anonimo', erro: 'Não foi possível falar com o servidor da Sora.' });
  });

  it('entrar guarda o token e carrega o usuário', async () => {
    rotas['POST /v1/auth/entrar'] = () => json(200, { token_acesso: 'tok' });
    rotas['GET /v1/eu'] = (init) => {
      expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok');
      return json(200, ANA);
    };
    await entrar(' ana@exemplo.com ', 'senha-muito-boa');
    expect(lerSessao().estado).toBe('logado');
    expect(JSON.parse(chamadas[0].init.body as string)).toEqual({ email: 'ana@exemplo.com', senha: 'senha-muito-boa' });
  });

  it('entrar com senha errada lança a mensagem do backend e continua anônimo', async () => {
    rotas['POST /v1/auth/renovar'] = () => json(401);
    await iniciarSessao();
    rotas['POST /v1/auth/entrar'] = () => json(401, { detail: 'E-mail ou senha incorretos.' });
    await expect(entrar('a@b.com', 'x')).rejects.toMatchObject({ mensagem: 'E-mail ou senha incorretos.' });
    expect(lerSessao().estado).toBe('anonimo');
  });

  it('cadastrar manda nome, email, senha e convite e já entra', async () => {
    rotas['POST /v1/auth/cadastrar'] = () => json(201);
    rotas['POST /v1/auth/entrar'] = () => json(200, { token_acesso: 'tok' });
    rotas['GET /v1/eu'] = () => json(200, ANA);
    await cadastrar({ nome: ' Ana Souza ', email: 'ana@exemplo.com', senha: '1234567890', convite: ' CONV ' });
    expect(JSON.parse(chamadas[0].init.body as string)).toEqual({ nome: 'Ana Souza', email: 'ana@exemplo.com', senha: '1234567890', convite: 'CONV' });
    expect(lerSessao().estado).toBe('logado');
  });

  it('sair chama o backend e volta a anônimo mesmo se ele falhar', async () => {
    rotas['POST /v1/auth/entrar'] = () => json(200, { token_acesso: 'tok' });
    rotas['GET /v1/eu'] = () => json(200, ANA);
    await entrar('ana@exemplo.com', 'x');
    rotas['POST /v1/auth/sair'] = () => json(500, { detail: 'erro' });
    await sair();
    expect(lerSessao().estado).toBe('anonimo');
    expect(chamadas.at(-1)?.url).toBe('/v1/auth/sair');
  });

  it('apagarConta usa DELETE /v1/conta com a senha', async () => {
    rotas['POST /v1/auth/entrar'] = () => json(200, { token_acesso: 'tok' });
    rotas['GET /v1/eu'] = () => json(200, ANA);
    await entrar('ana@exemplo.com', 'x');
    rotas['DELETE /v1/conta'] = () => json(204);
    await apagarConta('minha-senha');
    expect(JSON.parse(chamadas.at(-1)!.init.body as string)).toEqual({ senha: 'minha-senha' });
    expect(lerSessao().estado).toBe('anonimo');
  });

  it('renovação perdida durante o uso volta para Entrar', async () => {
    rotas['POST /v1/auth/entrar'] = () => json(200, { token_acesso: 'tok' });
    rotas['GET /v1/eu'] = () => json(200, ANA);
    await entrar('ana@exemplo.com', 'x');
    rotas['GET /v1/modelos'] = () => json(401);
    rotas['POST /v1/auth/renovar'] = () => json(401);
    await expect(api.get('/v1/modelos')).rejects.toMatchObject({ status: 401 });
    expect(lerSessao().estado).toBe('anonimo');
  });
});
