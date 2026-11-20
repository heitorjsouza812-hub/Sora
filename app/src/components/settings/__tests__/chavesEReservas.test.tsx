import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  listarChavesExtras: vi.fn(async (_p: string) => [{ id: 'c1', chave_final: '4321', criado_em: '2026-11-20T10:00:00Z' }]),
  adicionarChaveExtra: vi.fn(async (_p: string, _c: string) => ({ id: 'c2', chave_final: '9999', criado_em: '2026-11-20T11:00:00Z' })),
  removerChaveExtra: vi.fn(async (_p: string, _c: string) => {}),
  obterReservas: vi.fn(async () => [{ provedor_id: 'p-groq', modelo: 'groq/llama-3.3-70b' }]),
  definirReservas: vi.fn(async (itens: unknown[]) => itens),
  MAX_CHAVES_EXTRAS: 4,
  MAX_RESERVAS: 3,
}));
vi.mock('../../../api/reservas', () => api);
vi.mock('../../mascot', () => ({ SoraOrb: () => <span data-testid="orb" />, SoraThinking: () => <span data-testid="orb" /> }));
vi.mock('../../../state/modelos', () => ({
  modelosAtivos: () => [
    { provedor: 'groq', definicao: { nome: 'Groq' }, modelo: { provedor_id: 'p-groq', modelo: 'groq/llama-3.3-70b' } },
    { provedor: 'gemini', definicao: { nome: 'Google Gemini' }, modelo: { provedor_id: 'p-gem', modelo: 'gemini/gemini-2.5-flash' } },
  ],
  nomeAmigavelDoModelo: (m: { modelo: string }) => m.modelo.split('/').at(-1),
}));

import { ChavesExtras } from '../ChavesExtras';
import { ModelosReserva } from '../ModelosReserva';
import type { EstadoModelos } from '../../../state/modelos';

beforeEach(() => { vi.clearAllMocks(); });

describe('Chaves extras', () => {
  it('lista, adiciona e remove só pelo final da chave', async () => {
    const user = userEvent.setup();
    render(<ChavesExtras provedorId="p-groq" prefixo="gsk_" />);
    expect(await screen.findByText('Chave …4321')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Outra chave da API'), 'gsk_nova-chave-bem-longa');
    await user.click(screen.getByRole('button', { name: 'Testar e adicionar' }));
    expect(api.adicionarChaveExtra).toHaveBeenCalledWith('p-groq', 'gsk_nova-chave-bem-longa');
    expect(await screen.findByText('Chave …9999')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('gsk_nova-chave-bem-longa')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Remover chave …4321' }));
    expect(api.removerChaveExtra).toHaveBeenCalledWith('p-groq', 'c1');
    await waitFor(() => expect(screen.queryByText('Chave …4321')).toBeNull());
  });
});

describe('Modelos reserva', () => {
  it('carrega a lista, não deixa repetir e salva na ordem', async () => {
    const user = userEvent.setup();
    render(<ModelosReserva estado={{} as EstadoModelos} />);
    const primeira = screen.getByLabelText('1ª reserva') as HTMLSelectElement;
    await waitFor(() => expect(primeira.value).toBe('p-groq::groq/llama-3.3-70b'));
    const segunda = screen.getByLabelText('2ª reserva') as HTMLSelectElement;
    const repetida = within(segunda).getByRole('option', { name: 'Groq · llama-3.3-70b' }) as HTMLOptionElement;
    expect(repetida.disabled).toBe(true);
    await user.selectOptions(segunda, 'p-gem::gemini/gemini-2.5-flash');
    await user.click(screen.getByRole('button', { name: 'Salvar reservas' }));
    expect(api.definirReservas).toHaveBeenCalledWith([
      { provedor_id: 'p-groq', modelo: 'groq/llama-3.3-70b' },
      { provedor_id: 'p-gem', modelo: 'gemini/gemini-2.5-flash' },
    ]);
    expect(await screen.findByText('Modelos reserva salvos.')).toBeInTheDocument();
  });
});
