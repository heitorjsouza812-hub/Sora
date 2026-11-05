import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const post = vi.hoisted(() => vi.fn());
const buscarAutenticado = vi.hoisted(() => vi.fn());
vi.mock('../../../api/cliente', async (importar) => ({ ...(await importar<typeof import('../../../api/cliente')>()), api: { post, get: vi.fn() }, buscarAutenticado }));

import { receberEventoEquipe, reiniciarEquipe } from '../../../state/equipe';
import type { PassoTrabalho } from '../../../types';
import { RastroNavegador } from '../RastroNavegador';

const passo: PassoTrabalho = {
  id: 'p', agenteId: 'a1', tipo: 'ferramenta', texto: 'Abrindo', acao: 'navegador_abrir', ferramenta: 'navegador_abrir', status: 'executando', inicio: 1,
  resultado: { resumo: '', url: 'https://loja.com', titulo: 'Loja', rastro: { comando: 'click', args: ['@s1:e3'], ok: true, duracao_ms: 120 } },
};
afterEach(() => { post.mockReset(); buscarAutenticado.mockReset(); reiniciarEquipe(); });

describe('rastro do navegador', () => {
  it('mostra página e rastro redigido; assumir aba usa a rota de equipe.py e vira Devolver', async () => {
    receberEventoEquipe({ tipo: 'navegador.aba', dados: { aba_id: 'x', agente_id: 'a1', url: 'https://loja.com', titulo: 'Loja', carregada: true, assumida_pelo_usuario: false } });
    post.mockResolvedValue({ aba_id: 'x', agente_id: 'a1', url: 'https://loja.com', titulo: 'Loja', carregada: true, assumida_pelo_usuario: true });
    render(<RastroNavegador passo={passo} />);
    expect(screen.getByText('click @s1:e3')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Assumir aba' }));
    expect(post).toHaveBeenCalledWith('/v1/navegador/abas/x/assumir');
    expect(await screen.findByRole('button', { name: 'Devolver a aba' })).toBeTruthy();
  });

  it('carrega a captura pelo cliente autenticado', async () => {
    buscarAutenticado.mockResolvedValue({ blob: async () => new Blob(['x'], { type: 'image/png' }) });
    URL.createObjectURL = vi.fn(() => 'blob:cap'); URL.revokeObjectURL = vi.fn();
    render(<RastroNavegador passo={{ ...passo, status: 'concluido', resultado: { resumo: '', anexo_id: 'an1', nome: 'tela.png' } }} />);
    await waitFor(() => expect(screen.getByAltText('Captura da página: tela.png')).toBeTruthy());
    expect(buscarAutenticado).toHaveBeenCalledWith('/v1/anexos/an1', expect.anything());
  });
});
