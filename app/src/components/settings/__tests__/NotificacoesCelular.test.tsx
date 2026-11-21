import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const push = vi.hoisted(() => ({
  situacao: vi.fn(async (): Promise<string> => 'desligado'),
  ligar: vi.fn(async (): Promise<string> => 'ligado'),
  desligar: vi.fn(async (): Promise<string> => 'desligado'),
  testar: vi.fn(async () => ({ enviadas: 1 })),
}));
vi.mock('../../../push', () => push);
vi.mock('../../mascot', () => ({ SoraOrb: () => <span />, SoraThinking: () => <span /> }));

import { NotificacoesCelular } from '../NotificacoesCelular';

beforeEach(() => { vi.clearAllMocks(); push.situacao.mockResolvedValue('desligado'); });

describe('Notificações no celular', () => {
  it('liga, testa e desliga', async () => {
    const user = userEvent.setup();
    render(<NotificacoesCelular />);
    await user.click(await screen.findByRole('button', { name: 'Ligar' }));
    expect(push.ligar).toHaveBeenCalled();
    expect(await screen.findByText('Ligado neste aparelho.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Enviar teste' }));
    expect(await screen.findByText('Aviso de teste enviado.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Desligar' }));
    expect(await screen.findByRole('button', { name: 'Ligar' })).toBeInTheDocument();
  });

  it('explica o iPhone e o servidor sem push, sem botão de ligar', async () => {
    push.situacao.mockResolvedValue('precisa_instalar');
    const { unmount } = render(<NotificacoesCelular />);
    expect(await screen.findByText(/Adicionar à Tela de Início/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Ligar' })).toBeNull();
    unmount();
    push.situacao.mockResolvedValue('servidor_desligado');
    render(<NotificacoesCelular />);
    expect(await screen.findByText(/ainda não está ligada neste servidor/)).toBeInTheDocument();
  });
});
