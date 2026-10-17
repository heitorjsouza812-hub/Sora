import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { EstadoModelos, ModeloConfigurado } from '../../../state/modelos';

let estadoAtual: EstadoModelos;

vi.mock('../../../state/modelos', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../../state/modelos')>();
  return { ...original, useModelos: () => estadoAtual };
});

vi.mock('../../mascot', () => ({
  SoraOrb: () => <span data-testid="sora-orb" />,
}));

import { PROVEDORES_MODELO } from '../../../state/modelos';
import { ModelDefaults } from '../ModelDefaults';
import { ProviderCard } from '../ProviderCard';

const modelo = (patch: Partial<ModeloConfigurado> = {}): ModeloConfigurado => ({
  id: 'modelo-1',
  provedor_id: 'provedor-1',
  modelo: 'openai/lince-grande',
  nivel: 'N2',
  capacidades: ['texto'],
  contexto: 128000,
  preco_entrada: null,
  preco_saida: null,
  velocidade_tps: null,
  ativo: true,
  ...patch,
});

function criarEstado(modelos: ModeloConfigurado[]): EstadoModelos {
  const provedores = Object.fromEntries(PROVEDORES_MODELO.map(({ id }) => [id, {
    status: 'nao-conectado' as const,
    conexao: null,
    modelos: [],
  }])) as unknown as EstadoModelos['provedores'];
  provedores.openai = {
    status: 'conectado',
    conexao: {
      id: 'provedor-1', tipo: 'openai', base_url: null, chave_final: '1234',
      teto_mensal_usd: null, gasto_mes_usd: '0',
    },
    modelos,
  };
  return {
    versao: 2,
    padraoSora: null,
    padraoNovosAgentes: null,
    modelosPorAgente: {},
    provedores,
    modelos,
    prioridade: 'custo',
    carregando: false,
    carregado: true,
    erro: null,
  };
}

describe('nomes amigáveis dos modelos', () => {
  it('remove o prefixo técnico no cartão do provedor', () => {
    estadoAtual = criarEstado([modelo()]);

    render(<ProviderCard provedor={PROVEDORES_MODELO[0]} inicialmenteAberto />);

    expect(screen.getByText('lince-grande')).toBeInTheDocument();
    expect(screen.queryByText('openai/lince-grande')).not.toBeInTheDocument();
  });

  it('usa o nome de exibição e mantém o id completo no valor salvo', () => {
    estadoAtual = criarEstado([modelo({ nome_exibicao: 'Lince Grande' })]);

    render(<ModelDefaults estado={estadoAtual} />);

    const opcao = screen.getAllByRole('option', { name: 'OpenAI · Lince Grande' })[0] as HTMLOptionElement;
    expect(opcao.value).toBe('openai::openai/lince-grande');
  });
});
