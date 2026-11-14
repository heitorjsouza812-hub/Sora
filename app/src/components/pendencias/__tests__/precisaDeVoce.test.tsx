import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const resolver = vi.hoisted(() => vi.fn());
const ajustar = vi.hoisted(() => vi.fn());
const aceitar = vi.hoisted(() => vi.fn());
const recusar = vi.hoisted(() => vi.fn());
vi.mock('../../../api/grupos', async (importar) => {
  const original = await importar<typeof import('../../../api/grupos')>();
  return { ...original, resolverPedidoAtencao: resolver, ajustarPropostaGrupo: ajustar, aceitarPropostaGrupo: aceitar, recusarPropostaGrupo: recusar };
});

import { CartaoPrecisaDeVoce } from '../CartaoPrecisaDeVoce';
import { CartaoPropostaGrupo } from '../CartaoPropostaGrupo';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { _reiniciarAtencaoParaTestes, lerPrecisaDeVoce, receberPedidoAtencao } from '../../../state/atencao';
import { lerGrupos } from '../../../state/grupos';
import type { PedidoAtencao, PropostaGrupo } from '../tipos';

describe('cartões Precisa de você', () => {
  beforeEach(() => { resolver.mockReset(); ajustar.mockReset(); aceitar.mockReset(); recusar.mockReset(); _reiniciarAtencaoParaTestes(); });

  it('rascunho de envio oferece Enviar/Descartar e usa a decisão real', async () => {
    const pedido: PedidoAtencao = { id: 'p1', tipo: 'envio', titulo: 'Enviar e-mail', resumo: 'Para a cliente', grupoId: 'g1' };
    receberPedidoAtencao(pedido); resolver.mockResolvedValue(undefined);
    render(<CartaoPrecisaDeVoce pedido={pedido} />);
    expect(screen.getByRole('button', { name: 'Descartar' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Enviar' }));
    expect(resolver).toHaveBeenCalledWith(pedido, 'enviar', undefined);
    await waitFor(() => expect(lerPrecisaDeVoce().lista).toEqual([]));
  });

  it('aprovação oferece Aprovar/Recusar', () => {
    const pedido: PedidoAtencao = { id: 'p2', tipo: 'aprovacao', titulo: 'Abrir site', resumo: 'Ação externa' };
    receberPedidoAtencao(pedido); resolver.mockResolvedValue(undefined);
    render(<CartaoPrecisaDeVoce pedido={pedido} compacto />);
    fireEvent.click(screen.getByRole('button', { name: 'Recusar' }));
    expect(resolver).toHaveBeenCalledWith(pedido, 'recusar', undefined);
  });

  it('proposta distingue bots existentes e novos e só cria ao confirmar', async () => {
    const proposta: PropostaGrupo = { id: 'pr1', nome: 'Campanha', bots: [
      { id: 'b1', nome: 'Pesquisa', funcao: 'Pesquisar', cor: '#56A8FF', novo: false, selecionado: true },
      { nome: 'Texto', funcao: 'Escrever', cor: '#46E8A8', novo: true, selecionado: true },
    ] };
    ajustar.mockResolvedValue(undefined);
    aceitar.mockResolvedValue({ id: 'g9', nome: 'Campanha', membros: ['sora', 'b1', 'b2'], liderId: 'sora', precisaDeVoce: false, trabalhando: true });
    render(<MemoryRouter initialEntries={['/']}><Routes><Route path="/" element={<CartaoPropostaGrupo proposta={proposta} />} /><Route path="/grupos/:grupoId" element={<p>Tela do grupo</p>} /></Routes></MemoryRouter>);
    expect(screen.getByText(/já existe/)).toBeTruthy(); expect(screen.getByText('Escrever · novo')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Montar grupo' }));
    await waitFor(() => expect(ajustar).toHaveBeenCalled());
    expect(aceitar).toHaveBeenCalledWith('pr1');
    expect(await screen.findByText('Tela do grupo')).toBeTruthy();
    expect(lerGrupos().lista.map(grupo => grupo.id)).toContain('g9');
  });

  it('recusar a proposta não cria nada e avisa', async () => {
    const proposta: PropostaGrupo = { id: 'pr2', nome: 'Loja', bots: [
      { id: 'b1', nome: 'Pesquisa', funcao: 'Pesquisar', cor: '#56A8FF', novo: false, selecionado: true },
      { id: 'r1', nome: 'Texto', funcao: 'Escrever', cor: '#46E8A8', novo: true, selecionado: true },
    ] };
    recusar.mockResolvedValue(undefined);
    render(<MemoryRouter><CartaoPropostaGrupo proposta={proposta} /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: 'Recusar' }));
    expect(await screen.findByText(/Nenhum bot foi criado/)).toBeTruthy();
    expect(ajustar).not.toHaveBeenCalled(); expect(aceitar).not.toHaveBeenCalled();
  });
});
