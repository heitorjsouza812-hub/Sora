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

  it('mostra ferramentas com nome amigável e cores da paleta, sem a cor da Sora', () => {
    render(<MemoryRouter><CartaoRascunhoBot rascunho={{ ...rascunho, ferramentas: ['buscar_web', 'conector_x'] }} /></MemoryRouter>);
    fireEvent.click(screen.getByText(/^Ferramentas/));
    expect(screen.getByRole('button', { name: 'Buscar na web', pressed: true })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Conector x', pressed: true })).toBeInTheDocument();
    expect(screen.queryByText('buscar_web')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Cor #E2ECFF' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Cor #AC80FF' })).toBeInTheDocument();
  });

  it('converte rotina "Dias úteis" + hora no cron do backend e ajusta a cor', async () => {
    const confirmar = vi.spyOn(botsApi, 'confirmarRascunhoBot').mockResolvedValue({
      id: 'bot-2', tipo: 'individual', nome: 'Lume', funcao: 'Pesquisar referências', cor: '#AC80FF',
      movimento: 'gira', ferramentas: ['buscar_web'], estado: 'livre',
    });
    render(<MemoryRouter><CartaoRascunhoBot rascunho={rascunho} /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: 'Cor #AC80FF' }));
    fireEvent.click(screen.getByText(/^Rotina/));
    fireEvent.change(screen.getByLabelText('Quando'), { target: { value: 'uteis' } });
    fireEvent.change(screen.getByLabelText('Hora'), { target: { value: '08:30' } });
    fireEvent.change(screen.getByLabelText('O que fazer'), { target: { value: 'Resumir as novidades' } });
    fireEvent.click(screen.getByRole('button', { name: 'Criar bot' }));
    await waitFor(() => expect(confirmar).toHaveBeenCalled());
    expect(confirmar.mock.calls[0][1]).toMatchObject({ cor: '#AC80FF', rotina: { descricao: 'Resumir as novidades', agendamento: '30 8 * * 1-5' } });
  });

  it('pede o que o bot faz quando há rotina sem descrição', async () => {
    const confirmar = vi.spyOn(botsApi, 'confirmarRascunhoBot');
    render(<MemoryRouter><CartaoRascunhoBot rascunho={rascunho} /></MemoryRouter>);
    fireEvent.click(screen.getByText(/^Rotina/));
    fireEvent.change(screen.getByLabelText('Quando'), { target: { value: 'diario' } });
    fireEvent.click(screen.getByRole('button', { name: 'Criar bot' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('o que o bot deve fazer');
    expect(confirmar).not.toHaveBeenCalled();
  });

  it('mostra a decisão que chegou por SSE sem sumir do chat', () => {
    render(<MemoryRouter><CartaoRascunhoBot rascunho={{ ...rascunho, resolucao: { status: 'confirmado', agenteId: 'bot-9' } }} /></MemoryRouter>);
    expect(screen.getByText('Bot criado')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Criar bot' })).toBeNull();
    expect(screen.getByRole('link', { name: /Abrir conversa com Lume/ })).toHaveAttribute('href', '/bots/bot-9');
  });
});
