import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const HOJE = new Date(2026, 10, 20, 10, 0); // 20/11/2026, local
const api = vi.hoisted(() => ({
  obterAgenda: vi.fn(async (_de: Date, _ate: Date): Promise<unknown> => ({ previstas: [], feitas: [] })),
  obterFeed: vi.fn(async (): Promise<unknown> => ({ ligado: false, criado_em: null, url: null })),
  ligarFeed: vi.fn(async (): Promise<unknown> => ({ ligado: true, criado_em: '2026-11-20T10:00:00Z', url: 'https://api.sora.local/v1/agenda/feed/segredo.ics' })),
  desligarFeed: vi.fn(async () => {}),
}));
const pecas = vi.hoisted(() => ({ criarRotina: vi.fn(async (_r: unknown) => ({})) }));
vi.mock('../../../api/agenda', async (original) => ({ ...(await original<typeof import('../../../api/agenda')>()), ...api }));
vi.mock('../../../state/pecas', () => pecas);
vi.mock('../../../state/bots', () => ({ useBots: () => [{ id: 'b1', nome: 'Atlas', cor: '#56A8FF', funcao: '' }] }));
vi.mock('../../mascot', () => ({ SoraOrb: () => <span />, SoraThinking: () => <span /> }));

import { AgendaRotinas } from '../AgendaRotinas';
import { FeedAgenda } from '../FeedAgenda';

beforeEach(() => { vi.clearAllMocks(); vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(HOJE); });
afterEach(() => { vi.useRealTimers(); });

describe('Agenda das rotinas', () => {
  it('pede 6 semanas, mostra previstas e feitas no dia certo', async () => {
    api.obterAgenda.mockResolvedValue({
      previstas: [{ rotina_id: 'r1', agente_id: 'a', titulo: 'Resumo da manhã', quando: new Date(2026, 10, 21, 9, 0).toISOString() }],
      feitas: [{ rotina_id: 'r2', titulo: 'Conferir pedidos', iniciada_em: new Date(2026, 10, 19, 8, 0).toISOString(), status: 'falhou', origem: 'webhook' }],
    });
    render(<AgendaRotinas />);
    const [de, ate] = api.obterAgenda.mock.calls[0];
    expect((ate.getTime() - de.getTime()) / 86_400_000).toBeCloseTo(42, 0);
    expect(de.getDay()).toBe(0); // grade começa no domingo
    expect(await screen.findByText(/09:00 Resumo da manhã/)).toBeInTheDocument();
    expect(screen.getByText(/! Conferir pedidos/)).toBeInTheDocument();
  });

  it('clicar num dia futuro cria rotina toda semana nesse dia, com o bot escolhido', async () => {
    const user = userEvent.setup();
    render(<AgendaRotinas />);
    await user.click(await screen.findByRole('gridcell', { name: /sábado, 21 de novembro/i }));
    const form = screen.getByRole('form', { name: 'Nova rotina neste dia' });
    await user.type(within(form).getByLabelText('Título da rotina'), 'Backup');
    await user.type(within(form).getByLabelText('O que fazer'), 'Faça o backup.');
    await user.clear(within(form).getByLabelText('Hora'));
    await user.type(within(form).getByLabelText('Hora'), '07:30');
    await user.selectOptions(within(form).getByLabelText('Repetir'), 'semana');
    await user.selectOptions(within(form).getByLabelText('Quem faz'), 'b1');
    await user.click(within(form).getByRole('button', { name: 'Criar rotina' }));
    await waitFor(() => expect(pecas.criarRotina).toHaveBeenCalled());
    expect(pecas.criarRotina.mock.calls[0][0]).toMatchObject({ titulo: 'Backup', pedido: 'Faça o backup.', cron: '30 7 * * 6', agente_id: 'b1' });
    expect(api.obterAgenda).toHaveBeenCalledTimes(2); // recarrega depois de criar
  });

  it('dia que já passou não oferece criar', async () => {
    const user = userEvent.setup();
    render(<AgendaRotinas />);
    await user.click(await screen.findByRole('gridcell', { name: /quarta-feira, 18 de novembro/i }));
    expect(screen.queryByRole('form', { name: 'Nova rotina neste dia' })).toBeNull();
  });
});

describe('Assinar no calendário', () => {
  it('gera o endereço uma vez e depois só troca ou desliga', async () => {
    const user = userEvent.setup();
    render(<FeedAgenda />);
    await user.click(await screen.findByRole('button', { name: 'Gerar endereço' }));
    expect(await screen.findByText('https://api.sora.local/v1/agenda/feed/segredo.ics')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Trocar endereço' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Desligar' }));
    expect(api.desligarFeed).toHaveBeenCalled();
    expect(await screen.findByRole('button', { name: 'Gerar endereço' })).toBeInTheDocument();
    expect(screen.queryByText(/segredo\.ics/)).toBeNull();
  });
});
