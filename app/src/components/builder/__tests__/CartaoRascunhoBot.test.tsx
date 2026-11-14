import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import * as botsApi from '../../../api/bots';
import { CartaoRascunhoBot } from '../CartaoRascunhoBot';

vi.mock('../../mascot', () => ({ SoraOrb: () => <span data-testid="orb" /> }));

const rascunho: botsApi.RascunhoBotSaida = {
  id: 'rascunho-1', nome: 'Lume', funcao: 'Pesquisar referências', cor: '#56A8FF',
  instrucoes: 'Use fontes confiáveis.', ferramentas: ['buscar_web'], rotina: null, status: 'rascunho',
};

describe('CartaoRascunhoBot', () => {
  afterEach(() => vi.restoreAllMocks());

  it('permite ajustar e só cria ao confirmar', async () => {
    const confirmar = vi.spyOn(botsApi, 'confirmarRascunhoBot').mockResolvedValue({
      id: 'bot-1', tipo: 'individual', nome: 'Farol', funcao: 'Pesquisar referências', cor: '#56A8FF',
      movimento: 'gira', ferramentas: ['buscar_web'], estado: 'livre',
    });
    render(<MemoryRouter><CartaoRascunhoBot rascunho={rascunho} /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText('Nome'), { target: { value: 'Farol' } });
    fireEvent.click(screen.getByRole('button', { name: 'Criar bot' }));
    await waitFor(() => expect(confirmar).toHaveBeenCalledWith('rascunho-1', expect.objectContaining({ nome: 'Farol' })));
    expect(await screen.findByText('Bot criado')).toBeInTheDocument();
    expect(confirmar).toHaveBeenCalledWith('rascunho-1', expect.objectContaining({ rotina: null }));
    expect(screen.getByRole('link', { name: /Abrir conversa com Farol/ })).toHaveAttribute('href', '/bots/bot-1');
  });

  it('mostra a decisão que chegou por SSE sem sumir do chat', () => {
    render(<MemoryRouter><CartaoRascunhoBot rascunho={{ ...rascunho, resolucao: { status: 'confirmado', agenteId: 'bot-9' } }} /></MemoryRouter>);
    expect(screen.getByText('Bot criado')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Criar bot' })).toBeNull();
    expect(screen.getByRole('link', { name: /Abrir conversa com Lume/ })).toHaveAttribute('href', '/bots/bot-9');
  });
});
