// C3 (Vela-3) no navegador: nada de ponte com o PC; a tela só diz que é coisa do app de desktop.
import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock('../../api/cliente', async (importar) => ({ ...(await importar<typeof import('../../api/cliente')>()), api }));
vi.mock('../../state/bots', () => ({ useBots: () => [] }));

import { ComputadorPC } from '../../components/settings/ComputadorPC';
import { iniciarPontePc } from '../computadorPc';
import { aoPcParar, pcAutorizar, pcConta, pcExecutar, pcSair } from '../ponte';

it('no navegador a ponte não faz nada e o Rust nunca é chamado', async () => {
  const parar = iniciarPontePc();
  parar();
  expect(api.post).not.toHaveBeenCalled();
  await expect(pcConta('u1')).resolves.toBeNull();
  await expect(pcAutorizar('b1', true)).resolves.toBeNull();
  await expect(pcExecutar({ id: 'c', agente: { id: 'b', nome: 'B', cor: '#fff' }, operacao: 'observar', dados: {}, prazo_ms: 1 }))
    .resolves.toEqual({ ok: false, erro: { codigo: 'so_windows' } });
  await expect(pcSair()).resolves.toBeUndefined();
  expect(typeof aoPcParar(() => {})).toBe('function');
});

it('a tela no navegador diz que é só no app de desktop e mostra se ele está conectado', async () => {
  api.get.mockResolvedValue({ conectado: true, dispositivo: 'App de desktop da Sora (Windows)', vez: { agente_id: 'b1', nome: 'Atlas' } });
  render(<ComputadorPC />);
  expect(screen.getByText(/Disponível só no app de desktop/)).toBeTruthy();
  expect(await screen.findByText(/App de desktop conectado agora .* Atlas está usando o computador\./)).toBeTruthy();
  expect(api.get).toHaveBeenCalledWith('/v1/computador-pc/estado');
});
