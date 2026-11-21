import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AgenteBotSaida } from '../../../api/bots';

const BOTS: AgenteBotSaida[] = [
  { id: 'b-atlas', tipo: 'individual', nome: 'Atlas', funcao: 'Pesquisa', cor: '#56A8FF', movimento: 'vibracao', ferramentas: [], estado: 'livre' },
  { id: 'b-nina', tipo: 'individual', nome: 'Nina', funcao: 'Textos', cor: '#46E8A8', movimento: 'ondas', ferramentas: [], estado: 'livre' },
];
const api = vi.hoisted(() => ({ alterarRotina: vi.fn(async (_id: string, _patch: unknown): Promise<unknown> => ({})) }));
vi.mock('../../../state/pecas', async importar => ({ ...(await importar<object>()), alterarRotina: api.alterarRotina }));
vi.mock('../../../api/bots', async importar => ({ ...(await importar<object>()), listarBots: vi.fn(async () => BOTS) }));

import { RepasseRotina } from '../RepasseRotina';
import { _definirBotsParaTestes } from '../../../state/bots';
import type { Rotina } from '../../../state/pecas';

const ROTINA: Rotina = {
  id: 'r1', agente_id: 'b-atlas', conversa_id: null, titulo: 'Notícias', pedido: 'Junte as notícias.', tipo: 'cron', expressao: '0 8 * * *', fuso: null,
  proxima_execucao: null, ultima_execucao: null, silencioso: false, ativa: true, ultimo_status: null, criada_em: '2026-11-20T10:00:00Z',
  seguinte_agente_id: null, seguinte_pedido: null,
};

beforeEach(() => { vi.clearAllMocks(); _definirBotsParaTestes(BOTS); });

describe('Passar o resultado para outro bot', () => {
  it('escolhe o bot (sem o dono da rotina) e o pedido, e salva', async () => {
    const user = userEvent.setup();
    const aoMudar = vi.fn();
    api.alterarRotina.mockResolvedValue({ ...ROTINA, seguinte_agente_id: 'b-nina', seguinte_pedido: 'Escreva o post.' });
    render(<RepasseRotina rotina={ROTINA} aoMudar={aoMudar} />);
    await user.click(screen.getByRole('button', { name: 'Passar o resultado para outro bot' }));
    const lista = screen.getByLabelText('Passar o resultado para') as HTMLSelectElement;
    expect([...lista.options].map(o => o.textContent)).toEqual(['Nina']);
    const salvar = screen.getByRole('button', { name: 'Salvar' }) as HTMLButtonElement;
    expect(salvar.disabled).toBe(true);
    await user.type(screen.getByLabelText('O que ele faz com o resultado'), 'Escreva o post.');
    await user.click(salvar);
    expect(api.alterarRotina).toHaveBeenCalledWith('r1', { seguinte_agente_id: 'b-nina', seguinte_pedido: 'Escreva o post.' });
    expect(aoMudar).toHaveBeenCalledWith(expect.objectContaining({ seguinte_agente_id: 'b-nina' }));
  });

  it('mostra para quem vai e tira o repasse', async () => {
    const user = userEvent.setup();
    api.alterarRotina.mockResolvedValue({ ...ROTINA });
    render(<RepasseRotina rotina={{ ...ROTINA, seguinte_agente_id: 'b-nina', seguinte_pedido: 'Escreva o post.' }} aoMudar={vi.fn()} />);
    expect(screen.getByText('Nina')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Não passar adiante' }));
    expect(api.alterarRotina).toHaveBeenCalledWith('r1', { seguinte_agente_id: null });
  });
});
