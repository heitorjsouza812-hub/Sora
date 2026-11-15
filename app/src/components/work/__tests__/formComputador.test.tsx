import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../mascot', () => ({ SoraOrb: () => <span data-testid="orb" /> }));
const put = vi.hoisted(() => vi.fn());
const get = vi.hoisted(() => vi.fn());
vi.mock('../../../api/cliente', async (importar) => ({ ...(await importar<typeof import('../../../api/cliente')>()), api: { get, put, post: vi.fn() } }));

import { ferramentasParaSalvar } from '../../../data/ferramentas';
import { AgentConfigForm } from '../../builder/AgentConfigForm';
import type { RascunhoConstrutor } from '../../builder/types';

const base: RascunhoConstrutor = { id: 'b1', nome: 'Leo', funcao: 'Ajudante', descricaoCurta: '', cor: '#56A8FF', tipoMovimento: 'gira', ferramentas: ['buscar_web'], instrucoes: '', frasesIniciais: [], tom: 'objetivo', modelo: null };
afterEach(() => { cleanup(); put.mockReset(); get.mockReset(); });

describe('grupo "Computador e navegador" no formulário do bot', () => {
  it('o interruptor liga e desliga todas as ferramentas computador_* sem mexer nas outras', () => {
    get.mockResolvedValue([]);
    const onChange = vi.fn();
    const { rerender } = render(<MemoryRouter><AgentConfigForm rascunho={base} onChange={onChange} /></MemoryRouter>);
    fireEvent.click(screen.getByRole('checkbox', { name: /Computador próprio/ }));
    const ligado = onChange.mock.calls[0][0].ferramentas as string[];
    expect(ligado).toEqual(expect.arrayContaining(['buscar_web', 'computador_observar', 'computador_agir', 'computador_arquivos', 'computador_escrever_arquivo', 'computador_entregar_arquivo', 'computador_desligar']));
    expect(ferramentasParaSalvar(ligado)).toEqual(expect.arrayContaining(['falar', 'perguntar', 'computador_agir', 'buscar_web']));
    rerender(<MemoryRouter><AgentConfigForm rascunho={{ ...base, ferramentas: ligado }} onChange={onChange} /></MemoryRouter>);
    fireEvent.click(screen.getByRole('checkbox', { name: /Computador próprio/ }));
    expect(onChange.mock.calls[1][0].ferramentas).toEqual(['buscar_web']);
  });

  it('bot novo explica o navegador próprio; bot salvo troca o navegador pela rota', async () => {
    get.mockImplementation(async (u: string) => u.includes('/perfis') ? [{ perfil_id: 'p1', nome: 'Trabalho', tipo: 'nomeado', dominios_aprovados: [], criado_em: '', atualizado_em: '' }] : { agente_id: 'b1', tipo: 'agente', perfil_id: null, perfil_nome: null });
    put.mockResolvedValue({ agente_id: 'b1', tipo: 'compartilhado', perfil_id: null, perfil_nome: null });
    const { unmount } = render(<MemoryRouter><AgentConfigForm rascunho={{ ...base, id: undefined }} onChange={() => undefined} /></MemoryRouter>);
    expect(screen.getByText(/nasce com um navegador só dele/)).toBeTruthy();
    unmount();
    render(<MemoryRouter><AgentConfigForm rascunho={base} onChange={() => undefined} /></MemoryRouter>);
    const sel = await screen.findByRole('combobox', { name: 'Navegador do bot' });
    await waitFor(() => expect((sel as HTMLSelectElement).disabled).toBe(false));
    expect((sel as HTMLSelectElement).value).toBe('agente');
    fireEvent.change(sel, { target: { value: 'compartilhado' } });
    await waitFor(() => expect(put).toHaveBeenCalledWith('/v1/agentes/b1/navegador', { tipo: 'compartilhado' }));
  });
});
