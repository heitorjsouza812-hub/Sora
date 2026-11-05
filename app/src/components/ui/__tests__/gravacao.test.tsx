import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const transcrever = vi.hoisted(() => vi.fn());
vi.mock('../../../api/voz', async (importar) => ({ ...(await importar<typeof import('../../../api/voz')>()), transcreverAudio: transcrever }));

import { ErroApi } from '../../../api/cliente';
import { MSG_SEM_VOZ } from '../../../api/voz';
import { useGravacaoVoz } from '../useGravacaoVoz';

/** MediaRecorder mínimo: stop() emite um pedaço do tamanho combinado e fecha como o navegador faz. */
let bytes = 4000;
class RecFalso {
  static isTypeSupported = () => true;
  state: 'inactive' | 'recording' = 'inactive';
  mimeType = 'audio/webm';
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstart: (() => void) | null = null;
  onstop: (() => void) | null = null;
  start() { this.state = 'recording'; this.onstart?.(); }
  stop() { this.state = 'inactive'; this.ondataavailable?.({ data: new Blob([new Uint8Array(bytes)]) }); this.onstop?.(); }
}
beforeEach(() => { bytes = 4000; vi.stubGlobal('MediaRecorder', RecFalso); });
afterEach(() => { transcrever.mockReset(); vi.unstubAllGlobals(); });

const fala = {} as MediaStream;
function fluxo(stream: MediaStream | null) {
  const aoTexto = vi.fn();
  return { aoTexto, ...renderHook(({ s }: { s: MediaStream | null }) => useGravacaoVoz(s, aoTexto), { initialProps: { s: stream } }) };
}

describe('gravação do microfone → /v1/voz/transcrever', () => {
  it('ao parar o microfone, transcreve e entrega o texto ao campo', async () => {
    transcrever.mockResolvedValue('quero uma campanha de café');
    const { result, rerender, aoTexto } = fluxo(fala);
    rerender({ s: null });
    await waitFor(() => expect(aoTexto).toHaveBeenCalledWith('quero uma campanha de café'));
    expect(transcrever).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(result.current.transcrevendo).toBe(false));
    expect(result.current.erro).toBe('');
  });

  it('404 (sem provedor de voz): mostra o aviso em PT-BR e não escreve nada', async () => {
    transcrever.mockRejectedValue(new ErroApi(404, MSG_SEM_VOZ));
    const { result, rerender, aoTexto } = fluxo(fala);
    rerender({ s: null });
    await waitFor(() => expect(result.current.erro).toBe(MSG_SEM_VOZ));
    expect(aoTexto).not.toHaveBeenCalled();
  });

  it('enviar a mensagem com o microfone aberto descarta a fala em curso', () => {
    const { result, rerender } = fluxo(fala);
    act(() => result.current.descartarGravacao());
    rerender({ s: null });
    expect(transcrever).not.toHaveBeenCalled();
  });

  it('clique sem fala (áudio minúsculo) não chama a API', () => {
    bytes = 100;
    const { rerender } = fluxo(fala);
    rerender({ s: null });
    expect(transcrever).not.toHaveBeenCalled();
  });

  it('sem MediaRecorder no navegador não quebra', () => {
    vi.stubGlobal('MediaRecorder', undefined);
    const { result } = fluxo(fala);
    expect(result.current.transcrevendo).toBe(false);
  });
});
