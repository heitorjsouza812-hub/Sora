import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const LOGO = { id: 'a1', nome: 'logo.png', tipo: 'image/png', tamanho: 2048, origem: 'especialista', pasta_id: null, favorito: false, criado_em: '2026-11-20T10:00:00Z' };
const NOTAS = { id: 'a2', nome: 'notas.txt', tipo: 'text/plain', tamanho: 10, origem: 'usuario', pasta_id: 'p1', favorito: true, criado_em: '2026-11-19T10:00:00Z' };
const api = vi.hoisted(() => ({
  listarArquivos: vi.fn(async (_f: unknown): Promise<unknown> => ({ itens: [], proximo: null })),
  listarPastas: vi.fn(async (): Promise<unknown[]> => []),
  alterarArquivo: vi.fn(async (_id: string, patch: object): Promise<unknown> => ({ ...patch })),
  criarPasta: vi.fn(async (nome: string) => ({ id: 'p9', nome, total: 0, criada_em: '' })),
  renomearPasta: vi.fn(async () => ({})),
  apagarPasta: vi.fn(async () => {}),
  blobDoArquivo: vi.fn(async () => new Blob(['x'])),
}));
vi.mock('../../api/biblioteca', async (original) => ({ ...(await original<typeof import('../../api/biblioteca')>()), ...api }));
vi.mock('../../components/layout/AppShell', () => ({ AppShell: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
vi.mock('../../components/mascot', () => ({ SoraOrb: () => <span />, SoraThinking: () => <span /> }));

import Arquivos from '../Arquivos';

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }));
  api.listarArquivos.mockResolvedValue({ itens: [LOGO, NOTAS], proximo: null });
  api.listarPastas.mockResolvedValue([{ id: 'p1', nome: 'Campanha', total: 1, criada_em: '' }]);
});

describe('Arquivos', () => {
  it('lista os arquivos com tamanho, origem e prévia, e filtra por pasta e tipo', async () => {
    const user = userEvent.setup();
    render(<Arquivos />);
    expect(await screen.findByText('logo.png')).toBeInTheDocument();
    expect(screen.getByText(/2 KB · .* · feito por um bot/)).toBeInTheDocument();
    await waitFor(() => expect(api.blobDoArquivo).toHaveBeenCalledWith('a1')); // só a imagem ganha prévia
    expect(api.blobDoArquivo).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: /Campanha/ }));
    await waitFor(() => expect(api.listarArquivos).toHaveBeenLastCalledWith(expect.objectContaining({ pastaId: 'p1' })));
    await user.selectOptions(screen.getByLabelText('Tipo de arquivo'), 'imagem');
    await waitFor(() => expect(api.listarArquivos).toHaveBeenLastCalledWith(expect.objectContaining({ pastaId: 'p1', tipo: 'imagem' })));
  });

  it('favorita e move de pasta', async () => {
    api.alterarArquivo.mockImplementation(async (_id, patch) => ({ ...LOGO, ...patch }));
    const user = userEvent.setup();
    render(<Arquivos />);
    await user.click(await screen.findByRole('button', { name: 'Marcar logo.png como favorito' }));
    expect(api.alterarArquivo).toHaveBeenCalledWith('a1', { favorito: true });
    expect(await screen.findByRole('button', { name: 'Tirar logo.png dos favoritos' })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Pasta de logo.png'), 'p1');
    expect(api.alterarArquivo).toHaveBeenCalledWith('a1', { pasta_id: 'p1' });
  });

  it('cria pasta e apaga com confirmação, sem apagar arquivo', async () => {
    const user = userEvent.setup();
    render(<Arquivos />);
    await user.type(await screen.findByLabelText('Nome da nova pasta'), 'Notas fiscais{Enter}');
    expect(api.criarPasta).toHaveBeenCalledWith('Notas fiscais');
    await user.click(screen.getByRole('button', { name: /Campanha/ }));
    await user.click(await screen.findByRole('button', { name: 'Apagar pasta' }));
    const dialogo = await screen.findByRole('dialog');
    expect(within(dialogo).getByText(/voltam para "Sem pasta"/)).toBeInTheDocument();
    await user.click(within(dialogo).getByRole('button', { name: 'Apagar pasta' }));
    expect(api.apagarPasta).toHaveBeenCalledWith('p1');
  });
});
