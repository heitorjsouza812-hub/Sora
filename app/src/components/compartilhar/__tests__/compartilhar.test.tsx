import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { BotRetrato, Compartilhamento } from '../../../api/compartilhar';

const BOT: BotRetrato = {
  nome: 'Nina', funcao: 'Escreve posts', papel: '', cor: '#46E8A8', movimento: 'ondas', instrucoes: 'Tom leve.',
  ferramentas: ['buscar_web'], rotinas: [{ titulo: 'Post do dia', pedido: 'Escreva.', tipo: 'cron', expressao: '0 9 * * *', fuso: 'America/Sao_Paulo', silencioso: false }],
  habilidades: [{ nome: 'Legenda', descricao: 'Como escrever legenda', corpo: '1. Curta.' }],
};
const LINK: Compartilhamento = { codigo: 'abcdefgh1234', url: 'https://sora.app/b/abcdefgh1234', usos: 2, criado_em: '2026-11-20T10:00:00Z', bot: BOT };

const api = vi.hoisted(() => ({
  verCompartilhamento: vi.fn(async (_id: string): Promise<unknown> => null),
  compartilharBot: vi.fn(async (_id: string, _o: unknown): Promise<unknown> => ({})),
  pararDeCompartilhar: vi.fn(async (_id: string) => {}),
  exportarBot: vi.fn(async (_id: string, _n: string, _o: unknown) => {}),
  verBotPublico: vi.fn(async (_c: string): Promise<unknown> => ({})),
  importarBotLink: vi.fn(async (_c: string): Promise<unknown> => ({})),
  importarBotArquivo: vi.fn(),
}));
vi.mock('../../../api/compartilhar', () => api);
vi.mock('../../../state/pecas', async importar => ({
  ...(await importar<object>()),
  listarHabilidades: vi.fn(async () => [{ id: 'h1', nome: 'Legenda', descricao: '', corpo: '', origem: 'usuario', criada_em: '', atualizada_em: '' }]),
}));
vi.mock('../../mascot', () => ({ SoraOrb: () => <span data-testid="orb" /> }));
const sessao = vi.hoisted(() => ({ estado: 'logado' as 'logado' | 'anonimo' }));
vi.mock('../../../state/sessao', async importar => ({ ...(await importar<object>()), useSessao: () => sessao }));

import { CompartilharBot } from '../CompartilharBot';
import Compartilhado from '../../../screens/Compartilhado';

beforeEach(() => { vi.clearAllMocks(); sessao.estado = 'logado'; });

describe('Compartilhar bot', () => {
  it('cria o link com as opções escolhidas e para de compartilhar', async () => {
    const user = userEvent.setup();
    api.compartilharBot.mockResolvedValue(LINK);
    render(<CompartilharBot botId="b1" nome="Nina" aberto aoFechar={vi.fn()} />);
    expect(await screen.findByText('Este bot ainda não tem link.')).toBeInTheDocument();
    await user.click(await screen.findByLabelText('Legenda'));
    await user.click(screen.getByRole('button', { name: 'Criar link' }));
    expect(api.compartilharBot).toHaveBeenCalledWith('b1', { habilidades: ['h1'], com_rotinas: true });
    expect(await screen.findByText(LINK.url)).toBeInTheDocument();
    expect(screen.getByText(/2 pessoas usaram/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Baixar .zip' }));
    expect(api.exportarBot).toHaveBeenCalledWith('b1', 'Nina', { habilidades: ['h1'], com_rotinas: true });
    await user.click(screen.getByRole('button', { name: 'Parar de compartilhar' }));
    expect(api.pararDeCompartilhar).toHaveBeenCalledWith('b1');
    expect(await screen.findByText('Este bot ainda não tem link.')).toBeInTheDocument();
  });
});

function abrirPagina() {
  return render(<MemoryRouter initialEntries={['/compartilhado/abcdefgh1234']}><Routes>
    <Route path="/compartilhado/:codigo" element={<Compartilhado />} />
    <Route path="/bots/:agente" element={<p>Tela do bot</p>} />
  </Routes></MemoryRouter>);
}

describe('Página do bot compartilhado', () => {
  it('mostra o bot e, com login, cria a cópia e abre o bot', async () => {
    const user = userEvent.setup();
    api.verBotPublico.mockResolvedValue({ codigo: 'abcdefgh1234', criado_em: '2026-11-20T10:00:00Z', bot: BOT });
    api.importarBotLink.mockResolvedValue({ agente_id: 'novo', nome: 'Nina', rotinas: 1, habilidades: 1, avisos: [] });
    abrirPagina();
    expect(await screen.findByRole('heading', { name: 'Nina' })).toBeInTheDocument();
    expect(screen.getByText('Tom leve.')).toBeInTheDocument();
    expect(screen.getByText(/Todo dia às 09:00/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Usar este bot' }));
    expect(api.importarBotLink).toHaveBeenCalledWith('abcdefgh1234');
    expect(await screen.findByText('Tela do bot')).toBeInTheDocument();
  });

  it('sem login, pede para entrar antes de usar', async () => {
    const user = userEvent.setup();
    sessao.estado = 'anonimo';
    api.verBotPublico.mockResolvedValue({ codigo: 'abcdefgh1234', criado_em: '2026-11-20T10:00:00Z', bot: BOT });
    abrirPagina();
    await user.click(await screen.findByRole('button', { name: 'Entrar e usar este bot' }));
    expect(api.importarBotLink).not.toHaveBeenCalled();
  });

  it('link desligado avisa', async () => {
    api.verBotPublico.mockRejectedValue(new Error('Este link não existe mais.'));
    abrirPagina();
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Link indisponível' })).toBeInTheDocument());
  });
});
