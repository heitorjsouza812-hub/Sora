import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../mascot', () => ({ SoraOrb: () => <span data-testid="orb" /> }));
const api = vi.hoisted(() => ({ listarPedidosAtencao: vi.fn(), resolverPedidoAtencao: vi.fn(), listarGrupos: vi.fn(), listarMensagensGrupo: vi.fn(), listarTarefasGrupo: vi.fn() }));
vi.mock('../../../api/grupos', async (importar) => ({ ...(await importar<typeof import('../../../api/grupos')>()), ...api }));
const listarBots = vi.hoisted(() => vi.fn());
vi.mock('../../../api/bots', async (importar) => ({ ...(await importar<typeof import('../../../api/bots')>()), listarBots, obterSora: vi.fn().mockResolvedValue({ id: 'sora' }) }));

import { pedidoDaApi } from '../../../api/grupos';
import { _reiniciarAtencaoParaTestes, lerPrecisaDeVoce } from '../../../state/atencao';
import { _reiniciarBotsParaTestes } from '../../../state/bots';
import { _reiniciarGruposParaTestes } from '../../../state/grupos';
import { CentralPrecisaDeVoce } from '../CentralPrecisaDeVoce';

const bot = (id: string, nome: string, cor: string) => ({ id, tipo: 'individual', nome, funcao: 'Função', cor, movimento: 'gira', ferramentas: [], estado: 'livre' });
const PEDIDOS = [
  { id: 'p1', tipo: 'aprovacao', agente_id: 'b1', grupo_id: 'g1', titulo: 'Aprovar ação', resumo: 'Atlas quer enviar uma mensagem.', acao: 'gmail_enviar', opcoes: [] },
  { id: 'p2', tipo: 'aprovacao', agente_id: 'b2', grupo_id: null, titulo: 'Revisar acesso a domínio', resumo: 'Permitir acesso a banco.com?', acao: 'aprovacao', opcoes: [] },
  { id: 'p3', tipo: 'pergunta', agente_id: 'sora', grupo_id: null, titulo: '', resumo: '', pergunta: 'Qual público?', opcoes: [] },
];

beforeEach(() => {
  _reiniciarAtencaoParaTestes(); _reiniciarBotsParaTestes(); _reiniciarGruposParaTestes();
  Object.values(api).forEach(fn => fn.mockReset());
  listarBots.mockReset().mockResolvedValue([bot('b1', 'Atlas', '#56A8FF'), bot('b2', 'Luna', '#AC80FF')]);
  api.listarPedidosAtencao.mockImplementation(async () => PEDIDOS.map(pedido => pedidoDaApi(pedido)));
  api.listarGrupos.mockResolvedValue([{ id: 'g1', nome: 'Lançamento', membros: ['sora', 'b1', 'b2'], liderId: 'sora', precisaDeVoce: true, trabalhando: false }]);
  api.resolverPedidoAtencao.mockResolvedValue(undefined);
});

const montar = () => render(<MemoryRouter><CentralPrecisaDeVoce aberta onFechar={() => undefined} /></MemoryRouter>);

describe('central Precisa de você', () => {
  it('diz quantos pedidos esperam e não repete o rótulo dentro das faixas', async () => {
    montar();
    const dialogo = await screen.findByRole('dialog', { name: 'Precisa de você' });
    await within(dialogo).findByText('3 pedidos esperam uma decisão sua.');
    expect(within(dialogo).getAllByText('Precisa de você')).toHaveLength(1); // só o título do modal
  });

  it('lista todos os pedidos com a origem (bot, grupo e Sora) e as mesmas opções em todo lugar', async () => {
    montar();
    const dialogo = await screen.findByRole('dialog', { name: 'Precisa de você' });
    const cartoes = within(dialogo).getAllByRole('region', { name: 'Precisa de você' });
    expect(cartoes).toHaveLength(3);
    expect(within(cartoes[0]).getByText('Atlas')).toBeTruthy();
    expect(cartoes[0].textContent).toContain('grupo Lançamento');
    expect(within(cartoes[1]).getByText('Luna')).toBeTruthy();
    expect(within(cartoes[2]).getByText('Sora')).toBeTruthy();
    // ferramenta real: as três opções; domínio novo: só Permitir uma vez e Recusar.
    expect(within(cartoes[0]).getAllByRole('button').map(b => b.textContent)).toEqual(['Permitir uma vez', 'Sempre permitir', 'Recusar']);
    expect(within(cartoes[1]).getAllByRole('button').map(b => b.textContent)).toEqual(['Permitir uma vez', 'Recusar']);
    expect(within(dialogo).getByRole('link', { name: 'Abrir o grupo' }).getAttribute('href')).toBe('/grupos/g1');
  });

  it('Sempre permitir manda a decisão certa e o contador desce até zerar', async () => {
    montar();
    const dialogo = await screen.findByRole('dialog', { name: 'Precisa de você' });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Sempre permitir' }));
    await waitFor(() => expect(api.resolverPedidoAtencao).toHaveBeenCalledWith(expect.objectContaining({ id: 'p1' }), 'sempre_permitir', undefined));
    await waitFor(() => expect(lerPrecisaDeVoce().lista.map(p => p.id)).toEqual(['p2', 'p3']));
    fireEvent.click(within(dialogo).getAllByRole('button', { name: 'Recusar' })[0]);
    await waitFor(() => expect(api.resolverPedidoAtencao).toHaveBeenCalledWith(expect.objectContaining({ id: 'p2' }), 'recusar', undefined));
    fireEvent.change(await within(dialogo).findByPlaceholderText('Escreva sua resposta…'), { target: { value: 'Clientes novos' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Enviar' }));
    await waitFor(() => expect(api.resolverPedidoAtencao).toHaveBeenCalledWith(expect.objectContaining({ id: 'p3' }), 'responder', 'Clientes novos'));
    await waitFor(() => expect(lerPrecisaDeVoce().lista).toEqual([]));
    expect(await within(dialogo).findByText(/Nada espera por você agora/)).toBeTruthy();
  });
});
