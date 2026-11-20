import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../desktop/ponte', () => ({
  noDesktop: false,
  cofreLer: vi.fn(async () => null),
  cofreGravar: vi.fn(async () => {}),
  cofreApagar: vi.fn(async () => {}),
  janelaAtual: 'main',
  emitirSessao: vi.fn(async () => {}),
  pedirSessaoAoPrincipal: vi.fn(async () => null),
}));

import { _reiniciarClienteParaTestes, api, MSG_SEM_REDE } from '../../api/cliente';
import { _reiniciarSessaoParaTestes, apagarConta, cadastrar, entrar, iniciarSessao, lerSessao, baixarMeusDados, pedirLinkDeSenha, redefinirSenha, sair, tokenDoLink, trocarSenha } from '../sessao';

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
    expect(lerSessao()).toMatchObject({ estado: 'anonimo', erro: MSG_SEM_REDE });
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

  it('pedirLinkDeSenha manda o e-mail sem espaços e sem login', async () => {
    rotas['POST /v1/auth/esqueci-senha'] = () => json(202);
    await pedirLinkDeSenha('  ana@exemplo.com ');
    const { init } = chamadas.at(-1)!;
    expect(JSON.parse(init.body as string)).toEqual({ email: 'ana@exemplo.com' });
    expect(new Headers(init.headers).get('Authorization')).toBeNull();
  });

  it('redefinirSenha manda token e senha nova e tira quem estava entrado', async () => {
    rotas['POST /v1/auth/entrar'] = () => json(200, { token_acesso: 'tok' });
    rotas['GET /v1/eu'] = () => json(200, ANA);
    await entrar('ana@exemplo.com', 'x');
    rotas['POST /v1/auth/redefinir-senha'] = () => json(204);
    await redefinirSenha('tok-link', 'senha-nova-longa');
    expect(JSON.parse(chamadas.at(-1)!.init.body as string)).toEqual({ token: 'tok-link', senha_nova: 'senha-nova-longa' });
    expect(lerSessao().estado).toBe('anonimo');
  });

  it('link vencido mostra a mensagem do backend', async () => {
    rotas['POST /v1/auth/redefinir-senha'] = () => json(400, { detail: 'Este link de senha nova não vale mais.' });
    await expect(redefinirSenha('t', 'senha-nova-longa')).rejects.toMatchObject({ status: 400, mensagem: 'Este link de senha nova não vale mais.' });
  });

  it('trocarSenha usa POST /v1/conta/senha e continua entrado', async () => {
    rotas['POST /v1/auth/entrar'] = () => json(200, { token_acesso: 'tok' });
    rotas['GET /v1/eu'] = () => json(200, ANA);
    await entrar('ana@exemplo.com', 'x');
    rotas['POST /v1/conta/senha'] = () => json(204);
    await trocarSenha('atual-atual', 'nova-nova-nova');
    expect(JSON.parse(chamadas.at(-1)!.init.body as string)).toEqual({ senha_atual: 'atual-atual', senha_nova: 'nova-nova-nova' });
    expect(lerSessao().estado).toBe('logado');
  });

  it('tokenDoLink lê o token do fragmento', () => {
    expect(tokenDoLink('#token=abc-123')).toBe('abc-123');
    expect(tokenDoLink('')).toBe('');
    expect(tokenDoLink('#outra=1')).toBe('');
  });

  it('baixarMeusDados manda a senha e baixa o zip com o nome do servidor', async () => {
    rotas['POST /v1/auth/entrar'] = () => json(200, { token_acesso: 'tok' });
    rotas['GET /v1/eu'] = () => json(200, ANA);
    await entrar('ana@exemplo.com', 'x');
    rotas['POST /v1/conta/exportar'] = () => new Response(new Blob(['zip']), {
      status: 200, headers: { 'Content-Type': 'application/zip', 'Content-Disposition': 'attachment; filename="sora-meus-dados-2026-11-20.zip"' },
    });
    const criar = vi.fn(() => 'blob:x');
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: criar, revokeObjectURL: vi.fn() }));
    const clique = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      expect(this.download).toBe('sora-meus-dados-2026-11-20.zip');
    });
    await baixarMeusDados('minha-senha');
    const { init } = chamadas.at(-1)!;
    expect(JSON.parse(init.body as string)).toEqual({ senha: 'minha-senha' });
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer tok');
    expect(clique).toHaveBeenCalledOnce();
    clique.mockRestore();
  });

  it('baixarMeusDados com senha errada lança a mensagem do backend', async () => {
    rotas['POST /v1/conta/exportar'] = () => json(403, { detail: 'A senha está incorreta.' });
    await expect(baixarMeusDados('x')).rejects.toMatchObject({ status: 403, mensagem: 'A senha está incorreta.' });
  });
});
