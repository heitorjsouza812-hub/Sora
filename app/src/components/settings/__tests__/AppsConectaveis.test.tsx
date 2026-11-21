import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const APPS = [
  { id: 'canva', nome: 'Canva', descricao: 'Criar e editar designs.', categoria: 'Design', url: 'https://mcp.canva.com/mcp', conectado: false, conector_id: null },
  { id: 'notion', nome: 'Notion', descricao: 'Páginas e bases.', categoria: 'Docs', url: 'https://mcp.notion.com/mcp', conectado: true, conector_id: 'c9' },
];
const api = vi.hoisted(() => ({
  get: vi.fn(async (_c: string): Promise<unknown> => []),
  post: vi.fn(async (_c: string): Promise<unknown> => ({ url_autorizacao: 'https://www.canva.com/oauth?x=1' })),
}));
vi.mock('../../../api/cliente', async importar => ({ ...(await importar<object>()), api }));
vi.mock('../../mascot', () => ({ SoraOrb: () => <span />, SoraThinking: () => <span /> }));

import { AppsConectaveis } from '../AppsConectaveis';
import { ErroApi } from '../../../api/cliente';

beforeEach(() => { vi.clearAllMocks(); api.get.mockResolvedValue(APPS); });
afterEach(() => { vi.useRealTimers(); });

describe('Catálogo de apps', () => {
  it('lista os apps e abre o login do app escolhido', async () => {
    const user = userEvent.setup();
    const abrir = vi.spyOn(window, 'open').mockReturnValue(null);
    render(<AppsConectaveis />);
    expect(await screen.findByText('Canva')).toBeInTheDocument();
    expect(screen.getByText('● Conectado')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Conectar' }));
    expect(api.post).toHaveBeenCalledWith('/v1/conectores/apps/canva/conectar');
    expect(abrir).toHaveBeenCalledWith('https://www.canva.com/oauth?x=1', '_blank', 'noopener,noreferrer');
    expect(await screen.findByRole('button', { name: 'Esperando o login…' })).toBeInTheDocument();
  });

  it('erro ao começar o login aparece', async () => {
    const user = userEvent.setup();
    api.post.mockRejectedValueOnce(new ErroApi(502, 'Canva: Este app não aceita o cadastro automático da Sora.'));
    render(<AppsConectaveis />);
    await user.click(await screen.findByRole('button', { name: 'Conectar' }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/cadastro automático/));
  });
});
