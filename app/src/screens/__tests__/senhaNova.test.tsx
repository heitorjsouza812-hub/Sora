import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const acoes = vi.hoisted(() => ({
  pedirLinkDeSenha: vi.fn(async (_email: string) => {}),
  redefinirSenha: vi.fn(async (_token: string, _senha: string) => {}),
  entrar: vi.fn(async () => {}),
  cadastrar: vi.fn(async () => {}),
}));

vi.mock('../../components/mascot', () => ({ SoraOrb: () => <span data-testid="orb" /> }));
vi.mock('../../state/sessao', async (original) => ({
  ...(await original<typeof import('../../state/sessao')>()),
  useSessao: () => ({ estado: 'anonimo' }),
  pedirLinkDeSenha: acoes.pedirLinkDeSenha,
  redefinirSenha: acoes.redefinirSenha,
  entrar: acoes.entrar,
  cadastrar: acoes.cadastrar,
}));

import Entrar from '../Entrar';
import RedefinirSenha from '../RedefinirSenha';
import { ErroApi } from '../../api/cliente';

beforeEach(() => { vi.clearAllMocks(); });
afterEach(() => { window.history.replaceState(null, '', '/'); });

describe('Esqueci minha senha', () => {
  it('pede o link e mostra a mesma confirmação para qualquer e-mail', async () => {
    const user = userEvent.setup();
    render(<Entrar />);
    await user.click(screen.getByRole('button', { name: 'Esqueci minha senha' }));
    expect(screen.getByRole('heading', { name: 'Criar senha nova' })).toBeInTheDocument();
    await user.type(screen.getByLabelText('E-mail da conta'), 'ana@exemplo.com');
    await user.click(screen.getByRole('button', { name: 'Enviar link' }));
    expect(acoes.pedirLinkDeSenha).toHaveBeenCalledWith('ana@exemplo.com');
    expect(await screen.findByRole('status')).toHaveTextContent('Se existir uma conta com ana@exemplo.com');
    await user.click(screen.getByRole('button', { name: 'Voltar para Entrar' }));
    expect(screen.getByRole('heading', { name: 'Entrar na Sora' })).toBeInTheDocument();
  });

  it('mostra o erro do servidor (ex.: e-mail desligado)', async () => {
    acoes.pedirLinkDeSenha.mockRejectedValueOnce(new ErroApi(503, 'A recuperação de senha ainda não está ligada neste servidor.'));
    const user = userEvent.setup();
    render(<Entrar />);
    await user.click(screen.getByRole('button', { name: 'Esqueci minha senha' }));
    await user.type(screen.getByLabelText('E-mail da conta'), 'ana@exemplo.com');
    await user.click(screen.getByRole('button', { name: 'Enviar link' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('ainda não está ligada');
  });
});

describe('Criar senha nova pelo link', () => {
  it('lê o token do fragmento, tira ele da barra de endereço e salva', async () => {
    window.history.replaceState(null, '', '/redefinir-senha#token=tok-123');
    const user = userEvent.setup();
    render(<RedefinirSenha />);
    await waitFor(() => expect(window.location.hash).toBe(''));
    await user.type(screen.getByLabelText('Senha nova'), 'senha-nova-longa');
    await user.type(screen.getByLabelText('Repita a senha nova'), 'senha-nova-longa');
    await user.click(screen.getByRole('button', { name: 'Salvar senha nova' }));
    expect(acoes.redefinirSenha).toHaveBeenCalledWith('tok-123', 'senha-nova-longa');
    expect(await screen.findByRole('heading', { name: 'Senha nova criada' })).toBeInTheDocument();
  });

  it('não envia senhas diferentes', async () => {
    window.history.replaceState(null, '', '/redefinir-senha#token=tok-123');
    const user = userEvent.setup();
    render(<RedefinirSenha />);
    await user.type(screen.getByLabelText('Senha nova'), 'senha-nova-longa');
    await user.type(screen.getByLabelText('Repita a senha nova'), 'senha-nova-outra');
    expect(screen.getByText('As senhas estão diferentes.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Salvar senha nova' }));
    expect(acoes.redefinirSenha).not.toHaveBeenCalled();
  });

  it('link sem token avisa e não mostra o formulário', () => {
    window.history.replaceState(null, '', '/redefinir-senha');
    render(<RedefinirSenha />);
    expect(screen.getByRole('alert')).toHaveTextContent('Este link está incompleto');
    expect(screen.queryByLabelText('Senha nova')).toBeNull();
  });
});
