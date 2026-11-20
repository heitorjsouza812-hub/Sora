import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  enviarRelato: vi.fn(async (_texto: string, _diag: unknown) => ({ id: 'r1', resumo: 'x', com_diagnostico: true, criado_em: '2026-11-20T10:00:00Z' })),
  listarRelatos: vi.fn(async () => [{ id: 'r1', resumo: 'O bot travou.', com_diagnostico: true, criado_em: '2026-11-20T10:00:00Z' }]),
  retirarRelato: vi.fn(async (_id: string) => {}),
}));
vi.mock('../../../api/relatos', () => api);
vi.mock('../../mascot', () => ({ SoraOrb: () => <span data-testid="orb" />, SoraThinking: () => <span data-testid="orb" /> }));

import { RelatarProblema } from '../RelatarProblema';
import { RelatosEnviados } from '../RelatosEnviados';
import { abrirRelatarProblema, fecharRelatarProblema } from '../estado';
import { registrarErroRecente, _limparDiagnosticoParaTestes } from '../../../diagnostico';

beforeEach(() => { vi.clearAllMocks(); _limparDiagnosticoParaTestes(); });
afterEach(() => { act(() => fecharRelatarProblema()); });

describe('Relatar problema', () => {
  it('envia o texto com o diagnóstico que a pessoa pode ver antes', async () => {
    registrarErroRecente('api', 'GET /v1/bots → 500');
    const user = userEvent.setup();
    render(<RelatarProblema />);
    act(() => abrirRelatarProblema());
    await user.type(screen.getByLabelText('O que aconteceu?'), 'O bot travou.');
    await user.click(screen.getByText('Ver o que vai junto'));
    expect(screen.getByText(/GET \/v1\/bots → 500/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Enviar relato' }));
    expect(api.enviarRelato).toHaveBeenCalledOnce();
    const [texto, diagnostico] = api.enviarRelato.mock.calls[0];
    expect(texto).toBe('O bot travou.');
    expect(diagnostico).toMatchObject({ erros: [{ origem: 'api', mensagem: 'GET /v1/bots → 500' }] });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('sem a caixa marcada, o diagnóstico não vai', async () => {
    const user = userEvent.setup();
    render(<RelatarProblema />);
    act(() => abrirRelatarProblema());
    await user.type(screen.getByLabelText('O que aconteceu?'), 'Erro na tela.');
    await user.click(screen.getByRole('checkbox', { name: /Enviar diagnóstico/ }));
    expect(screen.queryByText('Ver o que vai junto')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Enviar relato' }));
    expect(api.enviarRelato).toHaveBeenCalledWith('Erro na tela.', null);
  });

  it('lista os relatos enviados e retira um', async () => {
    const user = userEvent.setup();
    render(<RelatosEnviados />);
    expect(await screen.findByText('O bot travou.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Retirar relato: O bot travou.' }));
    expect(api.retirarRelato).toHaveBeenCalledWith('r1');
    await waitFor(() => expect(screen.queryByText('O bot travou.')).toBeNull());
  });
});
