import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const post = vi.hoisted(() => vi.fn());
vi.mock('../../../api/cliente', async (importar) => {
  const original = await importar<typeof import('../../../api/cliente')>();
  return { ...original, api: { ...original.api, post } };
});
vi.mock('../../mascot', () => ({ SoraOrb: () => <span data-testid="sora-orb" /> }));

import { _definirEstadoParaTestes, _reiniciarProjetosParaTestes, lerEstado, type Pendencia } from '../../../state/projetos';
import { ListaPendencias } from '../Pendencias';

const pergunta: Pendencia = { tipo: 'pergunta', id: 'p1', conversaId: 'c1', texto: 'Quer continuar?', opcoes: [{ rotulo: 'Continuar', valor: 'continuar' }, { rotulo: 'Parar', valor: 'parar' }], respostaLivre: false, desde: 1 };
const aprovacao: Pendencia = { tipo: 'aprovacao', id: 'a1', conversaId: 'c1', resumo: 'Criar o agente Íris', dano: 'Passa a usar ferramentas', quemRecebe: null, expiraEm: 0, desde: 2 };

function comPendencias(...p: Pendencia[]) {
  _reiniciarProjetosParaTestes();
  _definirEstadoParaTestes({ ...lerEstado(), pendencias: p });
}
afterEach(() => { post.mockReset(); });

describe('cartões de pendência', () => {
  it('orçamento: Continuar e Parar chamam a rota de perguntas e o cartão sai', async () => {
    post.mockResolvedValue(undefined);
    comPendencias(pergunta);
    render(<ListaPendencias pendencias={[pergunta]} cor="#E2ECFF" />);
    fireEvent.click(screen.getByRole('button', { name: 'Continuar' }));
    expect(post).toHaveBeenCalledWith('/v1/perguntas/p1/responder', { valor: 'continuar' });
    await waitFor(() => expect(lerEstado().pendencias).toEqual([]));
  });

  it('aprovação: Aprovar, Sempre permitir e Recusar mandam a decisão certa', async () => {
    post.mockResolvedValue(undefined);
    comPendencias(aprovacao);
    render(<ListaPendencias pendencias={[aprovacao]} cor="#E2ECFF" />);
    expect(screen.getByText('Criar o agente Íris')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Recusar' }));
    expect(post).toHaveBeenCalledWith('/v1/aprovacoes/a1/decidir', { decisao: 'negar' });
    await waitFor(() => expect(lerEstado().pendencias).toEqual([]));
  });

  it('pergunta de resposta livre só envia texto preenchido', () => {
    post.mockResolvedValue(undefined);
    const livre: Pendencia = { ...pergunta, id: 'p2', opcoes: [], respostaLivre: true };
    comPendencias(livre);
    render(<ListaPendencias pendencias={[livre]} cor="#E2ECFF" />);
    const botao = screen.getByRole('button', { name: 'Responder' }) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
    fireEvent.change(screen.getByPlaceholderText('Escreva sua resposta…'), { target: { value: 'clientes novos' } });
    fireEvent.click(botao);
    expect(post).toHaveBeenCalledWith('/v1/perguntas/p2/responder', { valor: 'clientes novos' });
  });

  it('erro de envio mantém o cartão e mostra o aviso; 409 (já respondida) tira o cartão', async () => {
    const { ErroApi } = await import('../../../api/cliente');
    post.mockRejectedValueOnce(new Error('Sem conexão.'));
    comPendencias(pergunta);
    const { rerender } = render(<ListaPendencias pendencias={[pergunta]} cor="#E2ECFF" />);
    fireEvent.click(screen.getByRole('button', { name: 'Parar' }));
    await waitFor(() => expect(lerEstado().pendencias?.[0]?.erro).toBe('Sem conexão.'));
    rerender(<ListaPendencias pendencias={lerEstado().pendencias ?? []} cor="#E2ECFF" />);
    expect(screen.getByRole('alert').textContent).toContain('Sem conexão.');
    post.mockRejectedValueOnce(new ErroApi(409, 'Esta pergunta já foi respondida.'));
    fireEvent.click(screen.getByRole('button', { name: 'Parar' }));
    await waitFor(() => expect(lerEstado().pendencias).toEqual([]));
  });
});
