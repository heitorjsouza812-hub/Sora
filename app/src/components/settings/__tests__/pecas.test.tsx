import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock('../../../api/cliente', async (importar) => ({ ...(await importar<typeof import('../../../api/cliente')>()), api }));

import { SecaoConectores, SecaoMemoria, SecaoRotinas } from '../SecoesPecas';
afterEach(() => Object.values(api).forEach(f => f.mockReset()));

describe('seções de Configurações da etapa 4', () => {
  it('Memória lista, guarda e esquece pelas rotas do contrato', async () => {
    api.get.mockResolvedValue([{ id: 'm1', agente_id: null, conteudo: 'Fecha às segundas', tipo: 'fato', origem: 'usuario', travada: false, criada_em: '2026-11-02T10:00:00Z' }]);
    api.post.mockResolvedValue({}); api.delete.mockResolvedValue(undefined);
    render(<SecaoMemoria />);
    expect(await screen.findByText('Fecha às segundas')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Nova lembrança'), { target: { value: 'Moro em Curitiba' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/v1/memorias', { conteudo: 'Moro em Curitiba' }));
    fireEvent.click(screen.getByRole('button', { name: 'Esquecer' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/v1/memorias/m1'));
  });

  it('Memória mostra o motivo quando o servidor recusa (422)', async () => {
    api.get.mockResolvedValue([]);
    const { ErroApi } = await import('../../../api/cliente');
    api.post.mockRejectedValue(new ErroApi(422, 'Isso parece uma senha.'));
    render(<SecaoMemoria />);
    await screen.findByText('Nada guardado ainda.');
    fireEvent.change(screen.getByLabelText('Nova lembrança'), { target: { value: 'senha 123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect((await screen.findByRole('alert')).textContent).toContain('senha');
  });

  it('Rotinas cria com a cada + unidade e pausa com ativa:false', async () => {
    api.get.mockResolvedValue([{ id: 'r1', agente_id: null, conversa_id: null, titulo: 'Resumo', pedido: 'Resuma', tipo: 'intervalo', expressao: '1h', fuso: null, proxima_execucao: null, ultima_execucao: null, silencioso: false, ativa: true, ultimo_status: null, criada_em: '2026-11-02T10:00:00Z' }]);
    api.post.mockResolvedValue({}); api.patch.mockResolvedValue({});
    render(<SecaoRotinas />);
    await screen.findByText('Resumo');
    fireEvent.change(screen.getByLabelText('Título'), { target: { value: 'Bom dia' } });
    fireEvent.change(screen.getByLabelText('O que fazer'), { target: { value: 'Mande as notícias' } });
    fireEvent.click(screen.getByRole('button', { name: 'Criar rotina' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/v1/rotinas', { titulo: 'Bom dia', pedido: 'Mande as notícias', a_cada: 1, unidade: 'horas' }));
    fireEvent.click(screen.getByRole('button', { name: 'Pausar' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/v1/rotinas/r1', { ativa: false }));
  });

  it('Conectores testa e mostra o resultado, sem expor cabeçalhos', async () => {
    api.get.mockResolvedValue([{ id: 'c1', nome: 'Docs', url: 'https://x.com/mcp', ativo: true, tem_cabecalhos: true, estado: 'desconhecido', n_ferramentas: 0, ultimo_erro: null, criado_em: '2026-11-02T10:00:00Z' }]);
    api.post.mockResolvedValue({ ok: true, ferramentas: ['a', 'b'], erro: null });
    render(<SecaoConectores />);
    await screen.findByText('Docs');
    fireEvent.click(screen.getByRole('button', { name: 'Testar' }));
    expect(await screen.findByText('Funcionou: 2 ferramenta(s).')).toBeTruthy();
    expect(api.post).toHaveBeenCalledWith('/v1/conectores/c1/testar');
  });
});
