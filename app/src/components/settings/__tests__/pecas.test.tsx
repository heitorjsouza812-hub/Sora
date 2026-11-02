import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock('../../../api/cliente', async (importar) => ({ ...(await importar<typeof import('../../../api/cliente')>()), api }));

vi.mock('../../mascot', () => ({ SoraOrb: () => <span /> }));
import { SecaoConectores, SecaoMemoria, SecaoNavegador, SecaoRotinas } from '../SecoesPecas';
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

  const perfis = [
    { perfil_id: 'p1', nome: 'Trabalho', tipo: 'nomeado', dominios_aprovados: ['banco.com', 'loja.com'], criado_em: '2026-11-02T10:00:00Z', atualizado_em: '2026-11-02T10:00:00Z' },
    { perfil_id: 'p2', nome: 'Compartilhado', tipo: 'compartilhado', dominios_aprovados: [], criado_em: '2026-11-02T10:00:00Z', atualizado_em: '2026-11-02T10:00:00Z' },
  ];

  it('Navegador lista perfis com tipo e domínios aprovados e revoga um domínio', async () => {
    api.get.mockResolvedValue(perfis); api.delete.mockResolvedValue(undefined);
    render(<SecaoNavegador />);
    expect(await screen.findByText('Trabalho')).toBeTruthy();
    expect(screen.getByText('Perfil nomeado')).toBeTruthy();
    expect(screen.getByText('Compartilhado entre os agentes')).toBeTruthy();
    expect(screen.getByText('banco.com')).toBeTruthy();
    expect(screen.getByText('Nenhum domínio aprovado ainda.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Revogar loja.com em Trabalho' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/v1/navegador/perfis/p1/dominios/loja.com'));
    expect(api.get).toHaveBeenCalledWith('/v1/navegador/perfis');
  });

  it('Navegador só apaga o perfil depois da confirmação', async () => {
    api.get.mockResolvedValue(perfis); api.delete.mockResolvedValue(undefined);
    render(<SecaoNavegador />);
    await screen.findByText('Trabalho');
    fireEvent.click(screen.getAllByRole('button', { name: 'Apagar perfil' })[0]);
    expect(api.delete).not.toHaveBeenCalled();
    expect(await screen.findByText('Apagar este perfil?')).toBeTruthy();
    expect(screen.getByText(/voltam ao perfil compartilhado/)).toBeTruthy();
    const confirmar = screen.getAllByRole('button', { name: 'Apagar perfil' }).at(-1)!;
    fireEvent.click(confirmar);
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/v1/navegador/perfis/p1'));
  });

  it('Navegador mostra a explicação quando não há perfil e o erro do servidor', async () => {
    api.get.mockResolvedValue([]);
    const { unmount } = render(<SecaoNavegador />);
    expect(await screen.findByText(/Nenhum perfil com login salvo ainda/)).toBeTruthy();
    unmount();
    const { ErroApi } = await import('../../../api/cliente');
    api.get.mockRejectedValue(new ErroApi(500, 'Falha no servidor.'));
    render(<SecaoNavegador />);
    expect((await screen.findByRole('alert')).textContent).toContain('Falha no servidor.');
  });

  it('Navegador cria perfil pelo nome e mostra o aviso do 409 em PT-BR', async () => {
    api.get.mockResolvedValue([]);
    api.post.mockResolvedValueOnce({ ...perfis[0], dominios_aprovados: [] });
    render(<SecaoNavegador />);
    await screen.findByText(/Nenhum perfil com login salvo ainda/);
    fireEvent.change(screen.getByLabelText('Novo perfil'), { target: { value: 'Trabalho' } });
    fireEvent.click(screen.getByRole('button', { name: 'Criar perfil' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/v1/navegador/perfis', { nome: 'Trabalho' }));
    const { ErroApi } = await import('../../../api/cliente');
    api.post.mockRejectedValueOnce(new ErroApi(409, 'x'));
    fireEvent.change(screen.getByLabelText('Novo perfil'), { target: { value: 'Trabalho' } });
    fireEvent.click(screen.getByRole('button', { name: 'Criar perfil' }));
    expect((await screen.findByRole('alert')).textContent).toContain('Já existe um perfil com esse nome');
  });

  it('Navegador abre o site para entrar (aba assumida) e conclui fechando a aba', async () => {
    api.get.mockResolvedValue([perfis[0]]);
    api.post.mockResolvedValue({ aba_id: 'aba1', agente_id: 'a1', url: 'https://banco.com/entrar', titulo: 'Banco', carregada: true, assumida_pelo_usuario: true, fechada: false, pedido_de_ajuda: null });
    api.delete.mockResolvedValue(undefined);
    render(<SecaoNavegador />);
    await screen.findByText('Trabalho');
    const abrir = screen.getByRole('button', { name: 'Abrir para entrar' });
    expect((abrir as HTMLButtonElement).disabled).toBe(true); // só http/https
    fireEvent.change(screen.getByLabelText(/Site para entrar em/), { target: { value: 'banco.com' } });
    expect((abrir as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/Site para entrar em/), { target: { value: 'https://banco.com/entrar' } });
    fireEvent.click(abrir);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/v1/navegador/perfis/p1/abrir', { url: 'https://banco.com/entrar' }));
    expect(await screen.findByText(/Aba aberta para você entrar/)).toBeTruthy();
    expect(screen.getByText(/Banco/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Concluir e fechar' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/v1/navegador/abas/aba1'));
    await waitFor(() => expect(screen.queryByText(/Aba aberta para você entrar/)).toBeNull());
  });
});
