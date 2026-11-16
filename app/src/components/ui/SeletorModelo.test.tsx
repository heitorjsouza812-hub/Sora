import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';
import { AUTOMATICO, lerPreferencias, gravarPreferencias } from '../../api/preferenciasConversa';
import { api, ErroApi } from '../../api/cliente';
import { PreferenciasDaConversa, SeloAcessoTotal } from '../../state/preferenciasConversa';
import { SeletorModelo } from './SeletorModelo';
vi.mock('./useMedia', () => ({ useCelular: () => false }));
vi.mock('../../state/modelos', () => ({
  PROVEDORES_MODELO: [{ id: 'groq', nome: 'Groq' }],
  nomeAmigavelDoModelo: (m: { modelo: string }) => m.modelo,
  useModelos: () => ({ provedores: { groq: { conexao: { id: 'p' } } }, modelos: [
    { id: '1', modelo: 'Pensador', provedor_id: 'p', ativo: true, capacidades: ['visao', 'ferramentas'], rapido: true, raciocinio: ['baixo', 'alto'] },
    { id: '2', modelo: 'Simples', provedor_id: 'p', ativo: true, capacidades: [], raciocinio: [] },
  ] }),
}));
function Campo() { const [valor, mudar] = useState(AUTOMATICO); return <form><textarea aria-label="Mensagem" /><SeletorModelo controle={{ valor, mudar }} /><output>{JSON.stringify(valor)}</output></form>; }
beforeEach(() => vi.restoreAllMocks());
it('abre, busca, escolhe e esconde raciocínio sem níveis', () => {
  render(<Campo />); fireEvent.click(screen.getByRole('button', { name: 'Automático' }));
  fireEvent.change(screen.getByRole('textbox', { name: 'Buscar modelos' }), { target: { value: 'Pens' } });
  expect(screen.queryByText('Simples')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Pensador/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Alto' }));
  expect(screen.getByRole('status')).toHaveTextContent('alto');
  fireEvent.change(screen.getByRole('textbox', { name: 'Buscar modelos' }), { target: { value: '' } });
  fireEvent.click(screen.getByRole('button', { name: /Simples/ }));
  expect(screen.queryByText('Raciocínio')).not.toBeInTheDocument();
});
it('atalhos só atuam com popover aberto ou foco no compositor', () => {
  render(<Campo />); fireEvent.keyDown(document, { key: '1', ctrlKey: true });
  expect(screen.getByRole('status')).toHaveTextContent('"modelo":null');
  screen.getByRole('textbox').focus(); fireEvent.keyDown(document, { key: '1', ctrlKey: true });
  expect(screen.getByRole('status')).toHaveTextContent('Pensador');
});
it('acesso total exige confirmação e descreve bloqueios', () => {
  render(<Campo />); fireEvent.click(screen.getByRole('button', { name: 'Automático' }));
  fireEvent.change(screen.getByLabelText('Permissão'), { target: { value: 'total' } });
  expect(screen.getByRole('dialog')).toHaveTextContent('pagamentos');
  expect(screen.getByRole('status')).toHaveTextContent('perguntar');
  fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
  expect(screen.getByRole('status')).toHaveTextContent('perguntar');
  fireEvent.click(screen.getByRole('button', { name: 'Automático' }));
  fireEvent.change(screen.getByLabelText('Permissão'), { target: { value: 'total' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ativar acesso total' }));
  expect(screen.getByRole('status')).toHaveTextContent('total');
});
it('404 de leitura e escrita preserva o fallback automático', async () => {
  vi.spyOn(api, 'get').mockRejectedValue(new ErroApi(404, 'Não encontrado'));
  vi.spyOn(api, 'patch').mockRejectedValue(new ErroApi(404, 'Não encontrado'));
  expect(await lerPreferencias('/v1/conversas/c/preferencias')).toBeNull();
  expect(await gravarPreferencias('/v1/conversas/c/preferencias', AUTOMATICO)).toBeNull();
  render(<PreferenciasDaConversa conversaId="c"><SeletorModelo /><SeloAcessoTotal /></PreferenciasDaConversa>);
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  expect(screen.getByRole('button', { name: 'Automático' })).toBeInTheDocument();
  expect(screen.queryByText('Acesso total')).not.toBeInTheDocument();
});
it('selo reflete a preferência confirmada pelo servidor', async () => {
  vi.spyOn(api, 'get').mockResolvedValue({ ...AUTOMATICO, permissao: 'total' });
  render(<PreferenciasDaConversa conversaId="c"><SeloAcessoTotal /></PreferenciasDaConversa>);
  expect(await screen.findByRole('status')).toHaveTextContent('Acesso total');
});
it('422 mantém a escolha anterior e apresenta detail', async () => {
  vi.spyOn(api, 'get').mockResolvedValue(AUTOMATICO);
  vi.spyOn(api, 'patch').mockRejectedValue(new ErroApi(422, 'Modelo indisponível.'));
  render(<PreferenciasDaConversa conversaId="c"><SeletorModelo /></PreferenciasDaConversa>);
  fireEvent.click(screen.getByRole('button', { name: 'Automático' }));
  await waitFor(() => expect(screen.getByRole('button', { name: /Pensador/ })).not.toBeDisabled());
  fireEvent.click(screen.getByRole('button', { name: /Pensador/ }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Modelo indisponível.');
});
