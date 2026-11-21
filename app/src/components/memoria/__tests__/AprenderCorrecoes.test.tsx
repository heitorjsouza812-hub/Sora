import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  get: vi.fn(async (_caminho: string): Promise<unknown> => ({ a_cada: 20, opcoes: [0, 10, 20, 40] })),
  put: vi.fn(async (_caminho: string, corpo: { a_cada: number }): Promise<unknown> => ({ a_cada: corpo.a_cada, opcoes: [0, 10, 20, 40] })),
}));
vi.mock('../../../api/cliente', async importar => ({ ...(await importar<object>()), api }));

import { AprenderCorrecoes } from '../AprenderCorrecoes';

beforeEach(() => { vi.clearAllMocks(); });

describe('Aprender com correções', () => {
  it('mostra a frequência atual e muda para desligado', async () => {
    const user = userEvent.setup();
    render(<AprenderCorrecoes />);
    const campo = await screen.findByRole('combobox') as HTMLSelectElement;
    await waitFor(() => expect(campo.value).toBe('20'));
    expect([...campo.options].map(o => o.textContent)).toEqual(['Desligado', 'A cada 10 mensagens suas', 'A cada 20 mensagens suas', 'A cada 40 mensagens suas']);
    await user.selectOptions(campo, '0');
    expect(api.put).toHaveBeenCalledWith('/v1/memorias/aprendizado', { a_cada: 0 });
    await waitFor(() => expect(campo.value).toBe('0'));
  });
});
