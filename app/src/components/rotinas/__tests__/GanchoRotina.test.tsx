import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const BASE = { url: 'https://api.sora.local/v1/ganchos/rota-secreta', ativo: true, tipos_evento: ['pedido.pago'], criado_em: '2026-11-20T10:00:00Z', ultimo_recebido_em: null };
const api = vi.hoisted(() => ({
  obterGancho: vi.fn(async (_id: string): Promise<unknown> => null),
  criarGancho: vi.fn(async (_id: string, _tipos?: string[]): Promise<unknown> => ({})),
  alterarGancho: vi.fn(async (_id: string, patch: { ativo?: boolean }): Promise<unknown> => ({ ...patch })),
  apagarGancho: vi.fn(async (_id: string) => {}),
  testarGancho: vi.fn(async (_id: string) => ({ status: 'aceita', execucao_id: 'e1' })),
  entregasDoGancho: vi.fn(async (_id: string): Promise<unknown[]> => []),
  lerTipos: (t: string) => [...new Set(t.split(',').map(x => x.trim()).filter(Boolean))],
}));
vi.mock('../../../api/ganchos', () => api);

import { GanchoRotina } from '../GanchoRotina';

beforeEach(() => {
  vi.clearAllMocks();
  api.obterGancho.mockResolvedValue(null);
  api.criarGancho.mockResolvedValue({ ...BASE, segredo: 'whsec_segredo-de-teste' });
});

describe('Webhook da rotina', () => {
  it('liga com filtro e mostra o segredo uma vez', async () => {
    const user = userEvent.setup();
    render(<GanchoRotina rotinaId="r1" />);
    await user.type(await screen.findByLabelText('Só estes tipos de evento (opcional)'), 'pedido.pago, pedido.pago, ');
    await user.click(screen.getByRole('button', { name: 'Ligar webhook' }));
    expect(api.criarGancho).toHaveBeenCalledWith('r1', ['pedido.pago']);
    expect(await screen.findByText('whsec_segredo-de-teste')).toBeInTheDocument();
    expect(screen.getByText(BASE.url)).toBeInTheDocument();
    expect(screen.getByText(/Guarde o segredo agora/)).toBeInTheDocument();
  });

  it('já ligado: testa, pausa e desliga, sem mostrar segredo', async () => {
    api.obterGancho.mockResolvedValue(BASE);
    api.entregasDoGancho.mockResolvedValue([{ id: 'x', tipo_evento: 'pedido.pago', status: 'aceita', tamanho: 10, execucao_id: 'e', recebida_em: '2026-11-20T11:00:00Z' }]);
    api.alterarGancho.mockResolvedValue({ ...BASE, ativo: false });
    const user = userEvent.setup();
    render(<GanchoRotina rotinaId="r1" />);
    expect(await screen.findByText('Rodou')).toBeInTheDocument();
    expect(screen.queryByText(/whsec_/)).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Enviar teste' }));
    expect(await screen.findByText('Teste enviado: a rotina vai rodar agora.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Pausar' }));
    expect(api.alterarGancho).toHaveBeenCalledWith('r1', { ativo: false });
    expect(await screen.findByText('Pausado')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Desligar' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Ligar webhook' })).toBeInTheDocument());
    expect(api.apagarGancho).toHaveBeenCalledWith('r1');
  });
});
