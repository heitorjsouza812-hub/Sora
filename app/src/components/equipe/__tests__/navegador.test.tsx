import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
vi.mock('../../../api/cliente', async (importar) => ({ ...(await importar<typeof import('../../../api/cliente')>()), api }));

import { ErroApi } from '../../../api/cliente';
import { PerfilNavegadorDoAgente } from '../PerfilNavegadorDoAgente';

const perfil = { perfil_id: 'p1', nome: 'Trabalho', tipo: 'nomeado', dominios_aprovados: [], criado_em: '', atualizado_em: '' };
const comoAgente = (tipo: string, perfil_id: string | null = null, perfil_nome: string | null = null) => ({ agente_id: 'a1', tipo, perfil_id, perfil_nome });
afterEach(() => { api.get.mockReset(); api.put.mockReset(); });

function servidor(atual: ReturnType<typeof comoAgente>) {
  api.get.mockImplementation(async (c: string) => c.endsWith('/navegador') && c.includes('/agentes/') ? atual : [perfil, { ...perfil, perfil_id: 'pc', nome: 'Compartilhado', tipo: 'compartilhado' }]);
}

describe('perfil do navegador do agente', () => {
  it('mostra o perfil atual e só oferece perfis nomeados além de compartilhado e sem login', async () => {
    servidor(comoAgente('compartilhado'));
    render(<PerfilNavegadorDoAgente agenteId="a1" />);
    const seletor = await screen.findByLabelText('Perfil do navegador deste agente') as HTMLSelectElement;
    await waitFor(() => expect(seletor.disabled).toBe(false));
    expect(seletor.value).toBe('compartilhado');
    expect([...seletor.options].map(o => o.textContent)).toEqual(['Compartilhado entre os agentes', 'Sem login (aba descartável)', 'Trabalho']);
  });

  it('troca para um perfil e para sem login pelo PUT do contrato', async () => {
    servidor(comoAgente('compartilhado'));
    api.put.mockResolvedValueOnce(comoAgente('perfil', 'p1', 'Trabalho')).mockResolvedValueOnce(comoAgente('efemero'));
    render(<PerfilNavegadorDoAgente agenteId="a1" />);
    const seletor = await screen.findByLabelText('Perfil do navegador deste agente') as HTMLSelectElement;
    await waitFor(() => expect(seletor.disabled).toBe(false));
    fireEvent.change(seletor, { target: { value: 'perfil:p1' } });
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/v1/agentes/a1/navegador', { tipo: 'perfil', perfil_id: 'p1' }));
    await waitFor(() => expect(seletor.value).toBe('perfil:p1'));
    fireEvent.change(seletor, { target: { value: 'efemero' } });
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/v1/agentes/a1/navegador', { tipo: 'efemero' }));
    expect(await screen.findByText(/sem login salvo e sem pedir aprovação/)).toBeTruthy();
  });

  it('erro do servidor aparece e o seletor volta ao valor salvo', async () => {
    servidor(comoAgente('perfil', 'p1', 'Trabalho'));
    api.put.mockRejectedValue(new ErroApi(404, 'Perfil não encontrado.'));
    render(<PerfilNavegadorDoAgente agenteId="a1" />);
    const seletor = await screen.findByLabelText('Perfil do navegador deste agente') as HTMLSelectElement;
    await waitFor(() => expect(seletor.value).toBe('perfil:p1'));
    fireEvent.change(seletor, { target: { value: 'compartilhado' } });
    expect((await screen.findByRole('alert')).textContent).toContain('Perfil não encontrado.');
    expect(seletor.value).toBe('perfil:p1');
  });
});
