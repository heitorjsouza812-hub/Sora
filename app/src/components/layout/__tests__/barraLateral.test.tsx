import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const ctl = vi.hoisted(() => ({
  status: { orb: 'idle', rotulo: 'Sora', pulso: 0, fase: null } as { orb: string; rotulo: string; pulso: number; fase: string | null },
  abrirPaleta: vi.fn(),
}));

vi.mock('../../../state/sessao', () => ({
  useSessao: () => ({ estado: 'logado', usuario: { nome: 'Ana Souza', email: 'ana@sora.local', prioridade: 'qualidade', tem_provedor: true } }),
  sair: vi.fn(async () => {}),
  recarregarSessao: vi.fn(async () => {}),
}));
vi.mock('../../../state/projetos', () => ({
  useProjetos: () => ({ sora: { nome: 'Sora', cor: '#E2ECFF' }, projetos: [], agentes: {} }),
  useAgora: () => 0,
  novoChat: vi.fn(),
  estadoAgente: vi.fn(),
  estadoProjeto: vi.fn(),
}));
vi.mock('../useSoraStatus', async (importar) => ({ ...(await importar<typeof import('../useSoraStatus')>()), statusDaSora: () => ctl.status }));
vi.mock('../../mascot', () => ({ SoraOrb: ({ state }: { state?: string }) => <span data-testid="orb" data-state={state} /> }));
vi.mock('../../comandos', () => ({ Comandos: () => null, abrirPaleta: ctl.abrirPaleta, MOD: 'Ctrl' }));
vi.mock('../../grupos/NovoGrupo', () => ({ NovoGrupo: ({ aberto }: { aberto: boolean }) => aberto ? <div role="dialog" aria-label="Novo grupo" /> : null }));
vi.mock('../../erros', () => ({ FaixaErroEventos: () => null, FaixaSemConexao: () => null }));
vi.mock('../../builder', () => ({ EditorAgenteHost: () => null, MenuAgente: () => null }));
vi.mock('../../gestao', () => ({ GestaoHost: () => null, pedirApagar: vi.fn(), pedirRenomear: vi.fn() }));

import { consumirPedidoInicial } from '../../inicio';
import { _reiniciarAtencaoParaTestes } from '../../../state/atencao';
import { AppShell } from '../AppShell';
import { Sidebar } from '../Sidebar';

const Rota = () => { const l = useLocation(); return <output data-testid="rota" data-foco={String(!!(l.state as { focarCampo?: number } | null)?.focarCampo)}>{l.pathname}</output>; };
const montar = () => render(<MemoryRouter initialEntries={['/bots']}><Sidebar /><Rota /></MemoryRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  _reiniciarAtencaoParaTestes();
  ctl.status = { orb: 'idle', rotulo: 'Sora', pulso: 0, fase: null };
  consumirPedidoInicial();
});

describe('barra lateral (etapa 6)', () => {
  it('não tem o item "Precisa de você" e começa por "Criar novo", sem borda de campo', () => {
    montar();
    const barra = screen.getByRole('complementary', { name: 'Navegação principal' });
    expect(within(barra).queryByRole('button', { name: /Precisa de você/ })).toBeNull();
    const botoes = within(barra).getAllByRole('button');
    expect(botoes[0]).toHaveTextContent('Criar novo');
    expect(botoes[1]).toHaveTextContent('Buscar');
    expect(barra.querySelector('.shell-search')).toBeNull();
  });

  it('a marca mostra só o mascote e "Sora": sem subtítulo e sem estado quando parada', () => {
    montar();
    const marca = screen.getByRole('link', { name: 'Conversar com a Sora' });
    expect(marca).toHaveTextContent(/^Sora$/);
    expect(screen.queryByText('Chefe de equipe')).toBeNull();
    expect(marca.querySelector('.shell-ponto')).toBeNull();
    expect(within(marca).getByRole('status')).toBeEmptyDOMElement();
  });

  it('mostra um ponto discreto (com texto para leitor de tela) só quando a Sora trabalha ou espera por você', () => {
    ctl.status = { orb: 'coordinating', rotulo: 'Coordenando 2 agentes', pulso: 0, fase: 'coordenando' };
    const { unmount } = montar();
    const marca = screen.getByRole('link', { name: 'Conversar com a Sora' });
    expect(marca.querySelector('.shell-ponto.is-trabalhando')).not.toBeNull();
    expect(within(marca).getByRole('status')).toHaveTextContent('Coordenando 2 agentes');
    expect(marca).toHaveTextContent(/^Sora/);
    unmount();

    ctl.status = { orb: 'listening', rotulo: 'Aguardando você', pulso: 0, fase: null };
    montar();
    const espera = screen.getByRole('link', { name: 'Conversar com a Sora' });
    expect(espera.querySelector('.shell-ponto.is-precisa')).not.toBeNull();
    expect(within(espera).getByRole('status')).toHaveTextContent('Aguardando você');
  });

  it('o menu Criar novo tem três opções e fecha com Esc', async () => {
    const user = userEvent.setup();
    montar();
    await user.click(screen.getByRole('button', { name: 'Criar novo' }));
    const menu = await screen.findByRole('menu', { name: 'Criar novo' });
    expect(within(menu).getAllByRole('menuitem').map(i => i.textContent)).toEqual(['Novo bot', 'Novo grupo']);
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('menu')).toBeNull());
  });

  it('navega pelo menu com as setas e Enter', async () => {
    const user = userEvent.setup();
    montar();
    await user.click(screen.getByRole('button', { name: 'Criar novo' }));
    await screen.findByRole('menu', { name: 'Criar novo' });
    await waitFor(() => expect(screen.getByRole('menuitem', { name: 'Novo bot' })).toHaveFocus());
    await user.keyboard('{ArrowDown}{Enter}');
    expect(await screen.findByRole('dialog', { name: 'Novo grupo' })).toBeInTheDocument();
  });

  it('Novo bot abre sua tela independente', async () => {
    const user = userEvent.setup(); montar();
    await user.click(screen.getByRole('button', { name: 'Criar novo' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Novo bot' }));
    expect(screen.getByTestId('rota')).toHaveTextContent('/bots/novo');
    expect(consumirPedidoInicial()).toBeFalsy();
  });

  it('"Novo grupo" abre o Novo grupo', async () => {
    const user = userEvent.setup();
    montar();
    await user.click(screen.getByRole('button', { name: 'Criar novo' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Novo grupo' }));
    expect(await screen.findByRole('dialog', { name: 'Novo grupo' })).toBeInTheDocument();
  });

  it('o rodapé não mostra o e-mail', () => {
    montar();
    expect(screen.getByText('Ana Souza')).toBeInTheDocument();
    expect(screen.queryByText('ana@sora.local')).toBeNull();
  });

  it('o menu ☰ do celular tem a mesma marca e o mesmo item Criar novo', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><AppShell><p>Conteúdo</p></AppShell></MemoryRouter>);
    await user.click(screen.getByRole('button', { name: 'Abrir menu' }));
    const menu = screen.getByRole('dialog', { name: 'Menu' });
    const marca = within(menu).getByRole('link', { name: 'Conversar com a Sora' });
    expect(marca).toHaveTextContent(/^Sora$/);
    expect(within(menu).queryByText('Chefe de equipe')).toBeNull();
    expect(within(menu).getByRole('button', { name: 'Criar novo' })).toBeInTheDocument();
    expect(within(menu).queryByRole('button', { name: /Precisa de você/ })).toBeNull();
  });
});
