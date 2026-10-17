import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const acoes = vi.hoisted(() => ({ sair: vi.fn(async () => {}), novoChat: vi.fn() }));

vi.mock('../../../state/sessao', () => ({
  useSessao: () => ({
    estado: 'logado',
    usuario: { nome: 'Ana Souza', email: 'ana@sora.local', prioridade: 'qualidade', tem_provedor: false },
  }),
  sair: acoes.sair,
  recarregarSessao: vi.fn(async () => {}),
}));

vi.mock('../../../state/projetos', () => ({
  useProjetos: () => ({ sora: { nome: 'Sora', cor: '#E2ECFF' }, projetos: [], agentes: {} }),
  useAgora: () => 0,
  novoChat: acoes.novoChat,
  estadoAgente: vi.fn(),
  estadoProjeto: vi.fn(),
}));

vi.mock('../../../state/modelos', () => ({
  PROVEDORES_MODELO: [{ id: 'openai', nome: 'OpenAI' }],
}));

vi.mock('../../mascot', () => ({ SoraOrb: () => <span data-testid="sora-orb" /> }));
vi.mock('../../settings', () => ({ ProviderCard: ({ provedor }: { provedor: { nome: string } }) => <div>{provedor.nome}</div> }));
vi.mock('../../creditos', () => ({ IndicadorCreditos: () => null }));
vi.mock('../../gestao', () => ({ GestaoHost: () => null, pedirApagar: vi.fn(), pedirRenomear: vi.fn() }));
vi.mock('../../comandos', () => ({ Comandos: () => null }));
vi.mock('../../ilha', () => ({ Ilha: () => null }));
vi.mock('../../erros', () => ({ FaixaSemConexao: () => null }));
vi.mock('../../builder', () => ({ EditorAgenteHost: () => null, MenuAgente: () => null }));
vi.mock('../useSoraStatus', () => ({ statusDaSora: () => ({ orb: 'idle', pulso: 0, rotulo: 'Disponível' }), statusCurto: vi.fn() }));

import { AppShell } from '../AppShell';
import { Onboarding } from '../../sessao/Onboarding';

describe('acesso à conta', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('oferece Configurações, identidade da conta e Sair no menu móvel', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><AppShell><p>Conteúdo</p></AppShell></MemoryRouter>);

    await user.click(screen.getByRole('button', { name: 'Abrir menu' }));
    const menu = screen.getByRole('dialog', { name: 'Menu' });

    expect(within(menu).getByText('Ana Souza')).toBeInTheDocument();
    expect(within(menu).getByText('ana@sora.local')).toBeInTheDocument();
    expect(within(menu).getByRole('link', { name: 'Configurações' })).toHaveAttribute('href', '/configuracoes');

    const botaoSair = within(menu).getByRole('button', { name: 'Sair' });
    expect(botaoSair).toHaveClass('account-logout');
    await user.click(botaoSair);

    await waitFor(() => expect(acoes.sair).toHaveBeenCalledTimes(1));
    expect(acoes.novoChat).toHaveBeenCalledTimes(1);
  });

  it('permite sair diretamente do onboarding', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><Onboarding /></MemoryRouter>);

    const botaoSair = screen.getByRole('button', { name: 'Sair' });
    await user.click(botaoSair);

    await waitFor(() => expect(acoes.sair).toHaveBeenCalledTimes(1));
  });
});
