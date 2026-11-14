import { render } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { AvisosAtencao } from './AvisosAtencao';

const dados = vi.hoisted(() => ({ lista: [{ id: 'antigo', botId: 'b1' }], notificar: vi.fn() }));
vi.mock('../state/atencao', () => ({ usePrecisaDeVoce: () => ({ lista: dados.lista, carregado: true, erro: null }) }));
vi.mock('../state/bots', () => ({ useBots: () => [{ id: 'b1', nome: 'Bot' }] }));
vi.mock('../state/grupos', () => ({ useGrupos: () => ({ lista: [] }) }));
vi.mock('./notificacoes', () => ({ notificarAtencao: dados.notificar, tituloAtencao: vi.fn() }));
it('ignora pedidos iniciais e não repete pedido novo', () => {
  const abrir = vi.fn();
  const tela = render(<AvisosAtencao abrir={abrir} />);
  expect(dados.notificar).not.toHaveBeenCalled();
  dados.lista = [...dados.lista, { id: 'novo', botId: 'b1' }];
  tela.rerender(<AvisosAtencao abrir={abrir} />);
  tela.rerender(<AvisosAtencao abrir={abrir} />);
  expect(dados.notificar).toHaveBeenCalledTimes(1);
  expect(dados.notificar).toHaveBeenCalledWith(1, 'Bot', '/bots/b1', abrir);
});
