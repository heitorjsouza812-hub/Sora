import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ErroApi } from '../../../api/cliente';
import type { EstadoModelos, ModeloConfigurado } from '../../../state/modelos';

let estadoAtual: EstadoModelos;

vi.mock('../../../state/modelos', async importOriginal => {
  const original = await importOriginal<typeof import('../../../state/modelos')>();
  return { ...original, useModelos: () => estadoAtual };
});
vi.mock('../../mascot', () => ({ SoraOrb: () => <span data-testid="sora-orb" /> }));

import { PROVEDORES_MODELO } from '../../../state/modelos';
import { ProviderCard } from '../ProviderCard';

const modelo = (id: string, extra: Partial<ModeloConfigurado> = {}): ModeloConfigurado => ({
  id, provedor_id: 'pg', modelo: id, nivel: 'N2', capacidades: ['ferramentas'], contexto: 128000,
  preco_entrada: null, preco_saida: null, velocidade_tps: null, ativo: true, ...extra,
});

function criarEstado(modelos: ModeloConfigurado[]): EstadoModelos {
  const provedores = Object.fromEntries(PROVEDORES_MODELO.map(({ id }) => [id, { status: 'nao-conectado' as const, conexao: null, modelos: [] }])) as unknown as EstadoModelos['provedores'];
  provedores.gemini = { status: 'conectado', conexao: { id: 'pg', tipo: 'google', base_url: null, chave_final: '1234', teto_mensal_usd: null, gasto_mes_usd: '0' }, modelos };
  return { versao: 2, padraoSora: null, padraoNovosAgentes: null, modelosPorAgente: {}, provedores, modelos, prioridade: 'custo', carregando: false, carregado: true, erro: null };
}

const gemini = PROVEDORES_MODELO.find(p => p.id === 'gemini')!;
beforeEach(() => {
  vi.restoreAllMocks();
  estadoAtual = criarEstado([modelo('gemini-2.5-pro'), modelo('gemini-2.5-flash'), modelo('gemini-1.0-pro'), modelo('gemini-1.5-flash-8b', { principal: false })]);
});

describe('modelos do provedor: principais primeiro', () => {
  it('mostra os principais e deixa o resto atrás de "Ver todos (N)"', () => {
    render(<ProviderCard provedor={gemini} inicialmenteAberto />);
    expect(screen.getByText('Gemini 2.5 Pro')).toBeInTheDocument();
    expect(screen.getByText('Gemini 2.5 Flash')).toBeInTheDocument();
    expect(screen.queryByText('Gemini 1.0 Pro')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Ver todos (4)' }));
    expect(screen.getByText('Gemini 1.0 Pro')).toBeInTheDocument();
    expect(screen.getByText('Gemini 1.5 Flash 8B')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Só os principais' }));
    expect(screen.queryByText('Gemini 1.0 Pro')).not.toBeInTheDocument();
  });

  it('o campo `principal` do servidor decide quando existe', () => {
    estadoAtual = criarEstado([modelo('gemini-2.5-pro', { principal: false }), modelo('modelo-novo', { principal: true })]);
    render(<ProviderCard provedor={gemini} inicialmenteAberto />);
    expect(screen.getByText('Modelo Novo')).toBeInTheDocument();
    expect(screen.queryByText('Gemini 2.5 Pro')).not.toBeInTheDocument();
  });
});

describe('Adicionar modelo', () => {
  it('manda o id para o servidor', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValue(undefined as never);
    vi.spyOn(api, 'get').mockResolvedValue([] as never);
    render(<ProviderCard provedor={gemini} inicialmenteAberto />);
    const botao = screen.getByRole('button', { name: 'Adicionar modelo' });
    expect(botao).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: 'Id do modelo' }), { target: { value: ' gemini-3-pro ' } });
    fireEvent.click(botao);
    await waitFor(() => expect(post).toHaveBeenCalledWith('/v1/provedores/pg/modelos', { id: 'gemini-3-pro' }));
  });

  it('404 do servidor vira uma mensagem clara', async () => {
    vi.spyOn(api, 'post').mockRejectedValue(new ErroApi(404, 'Not Found'));
    render(<ProviderCard provedor={gemini} inicialmenteAberto />);
    fireEvent.change(screen.getByRole('textbox', { name: 'Id do modelo' }), { target: { value: 'gemini-3-pro' } });
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar modelo' }));
    expect(await screen.findByText(/ainda não permite adicionar modelos/)).toBeInTheDocument();
  });
});
