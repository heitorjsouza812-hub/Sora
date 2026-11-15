import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

const criar = vi.hoisted(() => vi.fn());
vi.mock('../../../api/grupos', async (importar) => {
  const original = await importar<typeof import('../../../api/grupos')>();
  return { ...original, criarGrupo: criar };
});
vi.mock('../../mascot', () => ({ SoraOrb: () => <span data-testid="sora-orb" /> }));
vi.mock('../../../state/bots', () => ({ useBots: () => [
  { id: 'b1', nome: 'Íris', cor: '#56A8FF', funcao: 'Pesquisa', estado: 'livre', ferramentas: [] },
  { id: 'b2', nome: 'Cora', cor: '#46E8A8', funcao: 'Texto', estado: 'trabalhando', ferramentas: [] },
] }));

import { NovoGrupo } from '../NovoGrupo';

describe('NovoGrupo', () => {
  it('mantém a Sora como chefe e exige de 2 a 5 bots', async () => {
    criar.mockResolvedValue({ id: 'g1', nome: 'Equipe', membros: ['b1', 'b2'], precisaDeVoce: false, trabalhando: false });
    const criado = vi.fn();
    render(<MemoryRouter><NovoGrupo aberto onFechar={() => undefined} onCriado={criado} /></MemoryRouter>);
    expect(screen.getByText('Chefe de equipe · sempre participa')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Nome do grupo'), { target: { value: 'Equipe' } });
    const botao = screen.getByRole('button', { name: 'Criar grupo' }) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/Íris/)); fireEvent.click(screen.getByLabelText(/Cora/));
    expect(botao.disabled).toBe(false); fireEvent.click(botao);
    await waitFor(() => expect(criar).toHaveBeenCalledWith({ nome: 'Equipe', membros: ['b1', 'b2'] }));
    expect(criado).toHaveBeenCalledWith('g1');
  });
});
