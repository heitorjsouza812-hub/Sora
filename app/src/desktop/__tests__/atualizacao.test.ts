import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const ponte = vi.hoisted(() => ({
  noDesktop: true,
  janelaAtual: 'main',
  verificarAtualizacao: vi.fn(async (): Promise<unknown> => ({ estado: 'em_dia', versao_atual: '0.1.0' })),
  instalarAtualizacao: vi.fn(async () => {}),
}));
const avisos = vi.hoisted(() => ({ toast: vi.fn() }));
vi.mock('../ponte', () => ponte);
vi.mock('../../components/base', () => avisos);

import { _reiniciarAtualizacaoParaTestes, iniciarVerificacaoDeAtualizacao, instalarAgora, procurarAtualizacao } from '../atualizacao';

beforeEach(() => { vi.useFakeTimers(); vi.clearAllMocks(); _reiniciarAtualizacaoParaTestes(); });
afterEach(() => { vi.useRealTimers(); });

describe('atualização do app de desktop', () => {
  it('procura 15 s depois de abrir e avisa uma vez por versão', async () => {
    ponte.verificarAtualizacao.mockResolvedValue({ estado: 'disponivel', versao_atual: '0.1.0', versao_nova: '0.2.0', notas: null });
    iniciarVerificacaoDeAtualizacao();
    expect(ponte.verificarAtualizacao).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(15_000);
    expect(avisos.toast).toHaveBeenCalledOnce();
    expect(avisos.toast.mock.calls[0][0]).toMatchObject({ mensagem: 'A versão 0.2.0 da Sora está pronta.', acao: { rotulo: 'Instalar e reiniciar' } });
    await vi.advanceTimersByTimeAsync(6 * 60 * 60 * 1000);
    expect(ponte.verificarAtualizacao).toHaveBeenCalledTimes(2);
    expect(avisos.toast).toHaveBeenCalledOnce(); // mesma versão: não repete
  });

  it('desligada (sem chave pública) não avisa nada', async () => {
    ponte.verificarAtualizacao.mockResolvedValue({ estado: 'desligada', versao_atual: '0.1.0' });
    expect(await procurarAtualizacao()).toEqual({ estado: 'desligada', versao_atual: '0.1.0' });
    expect(avisos.toast).not.toHaveBeenCalled();
  });

  it('falha ao instalar vira aviso com a mensagem do app', async () => {
    ponte.instalarAtualizacao.mockRejectedValueOnce('O instalador baixado não tem a assinatura da Sora. Nada foi instalado.');
    await instalarAgora();
    expect(avisos.toast).toHaveBeenCalledWith({ mensagem: 'O instalador baixado não tem a assinatura da Sora. Nada foi instalado.', tom: 'erro' });
  });
});
