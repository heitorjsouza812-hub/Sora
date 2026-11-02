import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const post = vi.hoisted(() => vi.fn());
vi.mock('../../../api/cliente', async (importar) => {
  const original = await importar<typeof import('../../../api/cliente')>();
  return { ...original, api: { ...original.api, post } };
});
vi.mock('../../mascot', () => ({ SoraOrb: () => <span /> }));

import { _definirEstadoParaTestes, _reiniciarProjetosParaTestes, lerEstado, type Pendencia } from '../../../state/projetos';
import { ListaPendencias } from '../Pendencias';

const dominio: Pendencia = {
  tipo: 'aprovacao', id: 'd1', conversaId: 'c1', resumo: 'Abrir banco.com', dano: '', quemRecebe: null, expiraEm: 0, desde: 1,
  revisaoDominio: { dominio: 'banco.com', url: 'https://banco.com/conta', perfil: { tipo: 'perfil', nome: 'Trabalho' }, agenteId: 'a1', opcoes: [{ rotulo: 'Aprovar domínio', valor: 'sempre_permitir' }, { rotulo: 'Negar', valor: 'negar' }] },
};
afterEach(() => post.mockReset());

describe('cartão de revisão de domínio', () => {
  it('mostra domínio, endereço e perfil, e decide pela rota de aprovações', () => {
    post.mockResolvedValue(undefined);
    _reiniciarProjetosParaTestes(); _definirEstadoParaTestes({ ...lerEstado(), pendencias: [dominio] });
    render(<ListaPendencias pendencias={[dominio]} cor="#E2ECFF" />);
    expect(screen.getByLabelText('Revisão de domínio')).toBeTruthy();
    expect(screen.getByText('banco.com')).toBeTruthy();
    expect(screen.getByText(/Trabalho/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Aprovar domínio' }));
    expect(post).toHaveBeenCalledWith('/v1/aprovacoes/d1/decidir', { decisao: 'sempre_permitir' });
  });
  it('Negar manda negar', () => {
    post.mockResolvedValue(undefined);
    _reiniciarProjetosParaTestes(); _definirEstadoParaTestes({ ...lerEstado(), pendencias: [dominio] });
    render(<ListaPendencias pendencias={[dominio]} cor="#E2ECFF" />);
    fireEvent.click(screen.getByRole('button', { name: 'Negar' }));
    expect(post).toHaveBeenCalledWith('/v1/aprovacoes/d1/decidir', { decisao: 'negar' });
  });
  it('perfil compartilhado (sem nome) aparece pelo tipo, e perfil nomeado pelo nome', () => {
    const compartilhado: Pendencia = { ...dominio, id: 'd2', revisaoDominio: { ...dominio.revisaoDominio!, perfil: { tipo: 'compartilhado', nome: null } } } as Pendencia;
    _reiniciarProjetosParaTestes(); _definirEstadoParaTestes({ ...lerEstado(), pendencias: [compartilhado] });
    render(<ListaPendencias pendencias={[compartilhado]} cor="#E2ECFF" />);
    expect(screen.getByText(/perfil compartilhado/)).toBeTruthy();
    expect(screen.queryByText(/“/)).toBeNull();
  });
});
