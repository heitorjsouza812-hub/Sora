import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock('../../../api/cliente', async (importar) => ({ ...(await importar<typeof import('../../../api/cliente')>()), api }));

import { ErroApi } from '../../../api/cliente';
import { mensagemPendencia } from '../../../state/pecas';
import { PendenciasDoAgente } from '../PendenciasDoAgente';

const p = (id: string, titulo: string, status: string, notas = '') => ({ id, agente_id: 'a1', titulo, notas, status, criada_em: '2026-11-02T10:00:00Z', atualizada_em: '2026-11-02T10:00:00Z' });
afterEach(() => Object.values(api).forEach(f => f.mockReset()));

describe('pendências do agente', () => {
  it('lista por status, com as concluídas recolhidas', async () => {
    api.get.mockResolvedValue([p('1', 'Ligar para o fornecedor', 'aberta', 'depois das 14h'), p('2', 'Revisar o orçamento', 'estacionada'), p('3', 'Enviar a nota', 'concluida')]);
    render(<PendenciasDoAgente agenteId="a1" />);
    expect(await screen.findByText('Ligar para o fornecedor')).toBeTruthy();
    expect(screen.getByText('depois das 14h')).toBeTruthy();
    expect(screen.getByText('Estacionadas (1)')).toBeTruthy();
    expect(screen.getByText('Concluídas (1)')).toBeTruthy();
    expect(api.get).toHaveBeenCalledWith('/v1/agentes/a1/pendencias?incluir_concluidas=true');
  });

  it('cria (estacionada se marcado), troca status, edita e apaga pelas rotas do contrato', async () => {
    api.get.mockResolvedValue([p('1', 'Ligar', 'aberta')]);
    api.post.mockResolvedValue(p('9', 'Nova', 'estacionada')); api.patch.mockResolvedValue(p('1', 'Ligar', 'concluida')); api.delete.mockResolvedValue(undefined);
    render(<PendenciasDoAgente agenteId="a1" />);
    await screen.findByText('Ligar');
    fireEvent.change(screen.getByLabelText('Nova pendência'), { target: { value: 'Nova' } });
    fireEvent.click(screen.getByLabelText('Criar como estacionada'));
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar pendência' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/v1/agentes/a1/pendencias', { titulo: 'Nova', notas: '', status: 'estacionada' }));

    fireEvent.change(screen.getByLabelText('Status de Ligar'), { target: { value: 'concluida' } });
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/v1/pendencias/1', { status: 'concluida' }));

    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
    const form = screen.getByRole('form', { name: /Editar pendência/ });
    fireEvent.change(within(form).getByLabelText('Título'), { target: { value: 'Ligar hoje' } });
    fireEvent.change(within(form).getByLabelText('Notas'), { target: { value: 'urgente' } });
    fireEvent.click(within(form).getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/v1/pendencias/1', { titulo: 'Ligar hoje', notas: 'urgente' }));

    fireEvent.click(await screen.findByRole('button', { name: 'Apagar' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/v1/pendencias/1'));
  });

  it('409 do limite vira aviso em PT-BR com o número e o que fazer', async () => {
    api.get.mockResolvedValue([]);
    api.post.mockRejectedValue(new ErroApi(409, 'Muitas pendências abertas.'));
    render(<PendenciasDoAgente agenteId="a1" />);
    await screen.findByText('Nenhuma pendência.');
    fireEvent.change(screen.getByLabelText('Nova pendência'), { target: { value: 'Mais uma' } });
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar pendência' }));
    const alerta = await screen.findByRole('alert');
    expect(alerta.textContent).toContain('100 pendências abertas');
    expect(alerta.textContent).toContain('Conclua ou apague');
    expect(mensagemPendencia(new ErroApi(404, 'Pendência não encontrada.'))).toBe('Pendência não encontrada.');
  });
});
