import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  comecarAEnsinar: vi.fn(async (_aba: string): Promise<unknown> => ({ gravando: true, passos: ['Abra https://loja.exemplo/'] })),
  verGravacao: vi.fn(async (_aba: string): Promise<unknown> => ({ gravando: false, passos: [] })),
  concluirEnsino: vi.fn(async (_aba: string, _o: string): Promise<unknown> => ({ nome: 'Buscar produto', descricao: 'Tarefa ensinada', corpo: '1. Abra a loja', passos: 3 })),
  cancelarEnsino: vi.fn(async (_aba: string) => {}),
}));
vi.mock('../../../api/ensinar', () => api);
const pecas = vi.hoisted(() => ({ criarHabilidade: vi.fn(async (_h: unknown): Promise<unknown> => ({})) }));
vi.mock('../../../state/pecas', async importar => ({ ...(await importar<object>()), criarHabilidade: pecas.criarHabilidade }));

vi.mock('../../mascot', () => ({ SoraOrb: () => <span data-testid="orb" />, SoraThinking: () => <span data-testid="orb" /> }));

import { EnsinarTarefa } from '../EnsinarTarefa';

beforeEach(() => { vi.clearAllMocks(); });

describe('Ensinar uma tarefa', () => {
  it('só aparece com a aba assumida', () => {
    const { container } = render(<EnsinarTarefa abaId="a1" assumida={false} />);
    expect(container.textContent).toBe('');
  });

  it('grava, conclui com o objetivo e salva só depois de revisar', async () => {
    const user = userEvent.setup();
    render(<EnsinarTarefa abaId="a1" assumida />);
    await user.click(screen.getByRole('button', { name: 'Ensinar esta tarefa' }));
    expect(api.comecarAEnsinar).toHaveBeenCalledWith('a1');
    expect(await screen.findByText(/Gravando · 1 passo/)).toBeInTheDocument();
    const concluir = screen.getByRole('button', { name: 'Concluir' }) as HTMLButtonElement;
    expect(concluir.disabled).toBe(true);
    await user.type(screen.getByLabelText('O que essa tarefa faz?'), 'Buscar produto');
    await user.click(concluir);
    expect(api.concluirEnsino).toHaveBeenCalledWith('a1', 'Buscar produto');
    expect(await screen.findByRole('dialog', { name: 'Nova habilidade' })).toBeInTheDocument();
    expect(pecas.criarHabilidade).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Salvar habilidade' }));
    await waitFor(() => expect(pecas.criarHabilidade).toHaveBeenCalledWith({ nome: 'Buscar produto', descricao: 'Tarefa ensinada', corpo: '1. Abra a loja' }));
  });

  it('cancelar desliga a gravação', async () => {
    const user = userEvent.setup();
    render(<EnsinarTarefa abaId="a1" assumida />);
    await user.click(screen.getByRole('button', { name: 'Ensinar esta tarefa' }));
    await user.click(await screen.findByRole('button', { name: 'Cancelar' }));
    expect(api.cancelarEnsino).toHaveBeenCalledWith('a1');
    expect(await screen.findByRole('button', { name: 'Ensinar esta tarefa' })).toBeInTheDocument();
  });
});
