import { act, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TrechoDestacado } from '../../comandos/PaletaComandos';
import { AvisosMemoria } from '../AvisosMemoria';
import { receberMemoriaCriada, reiniciarAvisosMemoria, rotaDoResultado, type ResultadoBusca } from '../../../state/pecas';

vi.mock('../../../api/cliente', async (orig) => ({ ...(await orig<object>()), api: { delete: vi.fn(async () => undefined), get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn() } }));

describe('Guardei isto', () => {
  it('mostra o chip só do bot dono e ignora repetição', () => {
    reiniciarAvisosMemoria();
    render(<AvisosMemoria agenteId="b1" />);
    expect(screen.queryByText('Guardei isto')).toBeNull();
    act(() => { receberMemoriaCriada({ memoria_id: 'm1', agente_id: 'b1', conversa_id: 'c', texto: 'Gosta de café' }); receberMemoriaCriada({ memoria_id: 'm1', agente_id: 'b1', texto: 'x' }); receberMemoriaCriada({ memoria_id: 'm2', agente_id: 'b2', texto: 'outro' }); });
    expect(screen.getAllByText('Guardei isto')).toHaveLength(1);
    expect(screen.getByText('Gosta de café')).toBeTruthy();
  });
});

describe('busca', () => {
  it('destaca os trechos e monta a rota', () => {
    const { container } = render(<TrechoDestacado trecho="o preço do café" destaques={[[2, 7], [11, 15]]} />);
    expect([...container.querySelectorAll('b')].map(b => b.textContent)).toEqual(['preço', 'café']);
    const base = { mensagem_id: 'M', conversa_id: 'c', grupo_id: null, seq: null, agente_id: null } as unknown as ResultadoBusca;
    expect(rotaDoResultado({ ...base, tipo: 'conversa' })).toBe('/#msg-M');
    expect(rotaDoResultado({ ...base, tipo: 'conversa', agente_id: 'a1' })).toBe('/bots/a1#msg-M');
    expect(rotaDoResultado({ ...base, tipo: 'grupo', grupo_id: 'g1' })).toBe('/grupos/g1#msg-M');
  });
});
