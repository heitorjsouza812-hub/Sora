import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
const rede = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), buscar: vi.fn() }));
vi.mock('../../../api/cliente', async original => ({ ...await original<typeof import('../../../api/cliente')>(), api: rede, buscarAutenticado: rede.buscar }));
vi.mock('../../../api/eventos', () => ({ acompanharEventos: vi.fn(() => new Promise(() => {})) }));
import { _definirEstadoParaTestes, _reiniciarProjetosParaTestes, avaliarMensagem, carregarMensagens, editarPergunta, gerandoNa, lerEstado, pararConversa, podeEditar, podeRefazer, refazerResposta, type MensagemChat as Mensagem } from '../../../state/projetos';
import { aplicarEvento } from '../../../state/aplicarEvento';
import { MensagemChat } from '../MensagemChat';
import { AnexoResposta } from '../AnexosResposta';
const fonte = { n: 1, titulo: 'Pesquisa', dominio: 'example.com', url: 'https://example.com/pesquisa' };
const pergunta: Mensagem = { id: 'p', conversaId: 'c', autor: 'usuario', texto: 'Pergunta', criadoEm: 1 };
const resposta: Mensagem = { id: 'r', conversaId: 'c', autor: 'sora', texto: 'Resposta [1]', criadoEm: 2 };
const apiMsg = (id: string, autor = 'sora', conteudo = 'Nova') => ({ id, conversa_id: 'c', autor, conteudo, criada_em: '2026-11-14T12:00:00Z', anexos: [], estado: 'concluida', fontes: [fonte], avaliacao: null });
function preparar() { _definirEstadoParaTestes({ ...lerEstado(), mensagens: [pergunta, resposta] }); }
afterEach(() => { cleanup(); _reiniciarProjetosParaTestes(); vi.clearAllMocks(); });

describe('contrato da conversa', () => {
  it('Parar usa a conversa e confirma interrupção pelo GET mesmo para pedido ainda na fila', async () => {
    preparar(); rede.post.mockResolvedValue(undefined); rede.get.mockResolvedValue([{ ...apiMsg('p', 'usuario'), estado: 'interrompida' }]);
    await pararConversa('c');
    expect(rede.post).toHaveBeenCalledWith('/v1/conversas/c/parar');
    expect(gerandoNa(lerEstado(), 'c', 0)).toBe(false);
    expect(lerEstado().mensagens.find(m => m.id === 'p')?.estado).toBe('interrompida');
  });
  it('fim mantém anexos, fontes e interrupção, sem duplicar texto na reentrega', () => {
    preparar(); let e = { ...lerEstado(), mensagens: [{ ...resposta, gerando: true }] };
    const fim = { id: '1', tipo: 'mensagem.fim', recebidoEm: 3, dados: { conversa_id: 'c', mensagem_id: 'r', estado: 'interrompida', fontes: [fonte], anexos: ['anexo'] } };
    e = aplicarEvento(e, fim) as typeof e; e = aplicarEvento(e, fim) as typeof e;
    e = aplicarEvento(e, { ...fim, tipo: 'mensagem.delta', dados: { ...fim.dados, texto: 'duplicado' } }) as typeof e;
    expect(e.mensagens).toHaveLength(1); expect(e.mensagens[0]).toMatchObject({ texto: 'Resposta [1]', gerando: false, estado: 'interrompida', fontes: [fonte], anexos: [{ id: 'anexo' }] });
  });
  it('GET restaura metadados e não deixa SSE antigo ressuscitar versão oculta', async () => {
    rede.get.mockResolvedValue([{ ...apiMsg('nova'), estado: 'interrompida', avaliacao: -1, anexos: ['a'] }]);
    await carregarMensagens('c');
    const e = lerEstado(); expect(e.mensagens[0]).toMatchObject({ estado: 'interrompida', avaliacao: 'negativa', fontes: [fonte], anexos: [{ id: 'a' }] });
    const repetido = aplicarEvento(e, { id: '1', tipo: 'mensagem.inicio', recebidoEm: Date.parse('2026-11-13T12:00:00Z'), dados: { conversa_id: 'c', mensagem_id: 'oculta', autor: 'sora' } });
    expect(repetido.mensagens).toHaveLength(1);
  });
  it.each(['refazer', 'editar'])('%s substitui pergunta e resposta e conserva resposta SSE que chega durante GET', async acao => {
    preparar(); rede.post.mockResolvedValue({ mensagem_id: 'p2' }); rede.patch.mockResolvedValue({ mensagem_id: 'p2' });
    rede.get.mockImplementation(async () => {
      _definirEstadoParaTestes({ ...lerEstado(), mensagens: [...lerEstado().mensagens, { ...resposta, id: 'r2', criadoEm: Date.parse('2026-11-14T12:00:01Z') }] });
      return [apiMsg('p2', 'usuario')];
    });
    if (acao === 'refazer') await refazerResposta('r'); else await editarPergunta('p', 'Corrigida');
    expect(lerEstado().mensagens.map(m => m.id)).toEqual(['p2', 'r2']);
    expect(lerEstado().mensagensOcultas).toEqual(['p', 'r']);
    expect(podeEditar(lerEstado(), lerEstado().mensagens[0]!)).toBe(true);
    expect(podeRefazer(lerEstado().mensagens[1]!)).toBe(true);
  });
  it('erro na edição conserva a versão atual e libera controles', async () => {
    preparar(); rede.patch.mockRejectedValueOnce(new Error('409'));
    await expect(editarPergunta('p', 'Nova')).rejects.toThrow('409');
    expect(lerEstado().mensagens).toEqual([pergunta, resposta]); expect(lerEstado().conversasOcupadas).toEqual([]);
  });
  it('avaliação só muda depois da persistência e segundo clique limpa', async () => {
    preparar(); rede.put.mockResolvedValueOnce({ ...apiMsg('r'), avaliacao: 1 }).mockResolvedValueOnce(apiMsg('r'));
    await avaliarMensagem('r', 'positiva'); expect(lerEstado().mensagens[1]?.avaliacao).toBe('positiva');
    await avaliarMensagem('r', 'positiva'); expect(lerEstado().mensagens[1]?.avaliacao).toBeUndefined();
    expect(rede.put).toHaveBeenLastCalledWith('/v1/conversas/c/mensagens/r/avaliacao', { valor: null });
  });
  it('chips são links seguros e citações apontam para chips, preservando código', async () => {
    render(<MensagemChat m={{ ...resposta, texto: 'Veja [1]. Código `[1]`.', fontes: [fonte, { ...fonte, n: 2, url: 'javascript:alert(1)' }] }} agora={0} />);
    await waitFor(() => expect(screen.getByRole('link', { name: 'Fonte 1' }).getAttribute('href')).toBe('#fonte-r-1'));
    const chip = screen.getByRole('link', { name: /Pesquisa/ }); expect(chip.getAttribute('rel')).toBe('noopener noreferrer'); expect(chip.getAttribute('target')).toBe('_blank');
    expect(document.querySelector('code')?.textContent).toBe('[1]'); expect(document.querySelectorAll('.msg-fontes a')).toHaveLength(1);
  });
  it('imagem usa blob autenticado, oferece ampliar/baixar e revoga URL ao desmontar', async () => {
    const criar = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:imagem'); const revogar = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    rede.buscar.mockResolvedValue({ blob: async () => new Blob(['imagem'], { type: 'image/png' }), headers: new Headers({ 'content-disposition': 'inline; filename="foto.png"' }) });
    const { unmount } = render(<AnexoResposta anexo={{ id: 'a', nome: 'Arquivo' }} />);
    await screen.findByRole('button', { name: 'Ampliar foto.png' }); expect(screen.getByRole('link', { name: 'Baixar foto.png' }).getAttribute('download')).toBe('foto.png');
    unmount(); expect(revogar).toHaveBeenCalledWith('blob:imagem'); criar.mockRestore(); revogar.mockRestore();
  });
});
