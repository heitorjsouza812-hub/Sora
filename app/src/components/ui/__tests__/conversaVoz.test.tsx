import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ get: vi.fn(), enviar: vi.fn(), transcrever: vi.fn(), falar: vi.fn(), parar: vi.fn(), e: { mensagens: [] as { id: string; autor: string; texto: string; gerando?: boolean }[], agentes: { bot: { conversaId: 'c' } } } }));
vi.mock('../../../api/cliente', () => ({ api: { get: mocks.get }, mensagemDeErro: (e: Error) => e.message }));
vi.mock('../../../api/voz', () => ({ MSG_SEM_VOZ: 'Conecte uma chave de voz.', sintetizarFala: mocks.falar, transcreverAudio: mocks.transcrever }));
vi.mock('../../../state/projetos', () => ({ useProjetos: () => mocks.e, lerEstado: () => mocks.e, gerandoNa: () => false, mensagensDa: () => mocks.e.mensagens, enviarParaAgente: mocks.enviar, pararConversa: mocks.parar }));
vi.mock('../../mascot', () => ({ SoraOrb: ({ state }: { state: string }) => <span data-testid="orb">{state}</span> }));
import { ConversaVoz } from '../ConversaVoz';
let nivel = .05;
let gravadores: Gravador[];
let audios: AudioFalso[];
const pararTrack = vi.fn(), getUserMedia = vi.fn();
class Gravador {
  static isTypeSupported() { return true; }
  state = 'inactive'; mimeType = 'audio/webm';
  onstop: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  constructor() { gravadores.push(this); }
  start() { this.state = 'recording'; }
  stop() { this.state = 'inactive'; this.ondataavailable?.({ data: new Blob(['audio']) }); this.onstop?.(); }
}
class AudioFalso {
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  pause = vi.fn(); play = vi.fn(async () => {});
  constructor() { audios.push(this); }
}
beforeEach(() => {
  vi.useFakeTimers(); gravadores = []; audios = []; nivel = .05;
  mocks.e = { mensagens: [], agentes: { bot: { conversaId: 'c' } } };
  mocks.get.mockResolvedValue([{ tipo: 'openai', chave_final: '1234' }]); mocks.enviar.mockResolvedValue(undefined); mocks.transcrever.mockResolvedValue('Olá'); mocks.falar.mockResolvedValue(new Blob(['fala']));
  getUserMedia.mockResolvedValue({ getTracks: () => [{ stop: pararTrack }] });
  vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } });
  vi.stubGlobal('MediaRecorder', Gravador); vi.stubGlobal('Audio', AudioFalso);
  vi.stubGlobal('AudioContext', class { createMediaStreamSource() { return { connect() {}, disconnect() {} }; } createAnalyser() { return { fftSize: 2048, getFloatTimeDomainData(a: Float32Array) { a.fill(nivel); } }; } close() { return Promise.resolve(); } });
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:voz'); vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.clearAllMocks(); });
const tela = () => <ConversaVoz agenteId="bot" cor="#56A8FF" movimento="gira" />;
async function iniciar() { await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Conversar por voz' })); }); }
async function falar() { await act(async () => { await vi.advanceTimersByTimeAsync(100); }); nivel = 0; await act(async () => { await vi.advanceTimersByTimeAsync(1550); }); }
describe('conversa por voz', () => {
  it('sem chave avisa antes de abrir o microfone', async () => {
    mocks.get.mockResolvedValue([]); render(tela()); await iniciar();
    expect(getUserMedia).not.toHaveBeenCalled(); expect(screen.getByRole('alert').textContent).toContain('chave');
  });
  it('microfone negado vira aviso de permissão, não erro de servidor', async () => {
    getUserMedia.mockRejectedValue(Object.assign(new Error('negado'), { name: 'NotAllowedError' })); render(tela()); await iniciar();
    expect(screen.getByRole('alert').textContent).toContain('Permita o uso do microfone'); expect(screen.getByRole('button', { name: 'Conversar por voz' })).toBeTruthy();
  });
  it('silêncio encerra fala, envia, toca resposta e volta a ouvir sozinho', async () => {
    const { rerender } = render(tela()); await iniciar(); expect(screen.getByTestId('orb').textContent).toBe('listening');
    await falar(); expect(mocks.transcrever).toHaveBeenCalledTimes(1); expect(mocks.enviar).toHaveBeenCalledWith('bot', 'Olá'); expect(pararTrack).toHaveBeenCalled(); expect(screen.getByTestId('orb').textContent).toBe('thinking');
    mocks.e = { ...mocks.e, mensagens: [{ id: 'r', autor: 'bot', texto: 'Resposta' }] }; rerender(tela());
    await act(async () => { await vi.advanceTimersByTimeAsync(500); }); expect(mocks.falar).toHaveBeenCalledWith('Resposta', expect.any(AbortSignal)); expect(audios[0]?.play).toHaveBeenCalled();
    await act(async () => { audios[0]?.onended?.(); }); expect(getUserMedia).toHaveBeenCalledTimes(2); expect(screen.getByTestId('orb').textContent).toBe('listening');
  });
  it.each(['Escape', 'toque'])('%s interrompe áudio e volta a ouvir; desmontagem libera captura', async modo => {
    const { rerender, unmount } = render(tela()); await iniciar(); await falar();
    mocks.e = { ...mocks.e, mensagens: [{ id: 'r', autor: 'bot', texto: 'Resposta' }] }; rerender(tela());
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    await act(async () => { if (modo === 'Escape') fireEvent.keyDown(window, { key: 'Escape' }); else fireEvent.click(screen.getByRole('button', { name: 'Interromper leitura' })); });
    expect(audios[0]?.pause).toHaveBeenCalled(); expect(getUserMedia).toHaveBeenCalledTimes(2);
    unmount(); expect(gravadores.at(-1)?.state).toBe('inactive');
  });
  it('sair durante transcrição impede envio tardio', async () => {
    let resolver!: (texto: string) => void; mocks.transcrever.mockReturnValue(new Promise<string>(r => { resolver = r; }));
    const { unmount } = render(tela()); await iniciar(); await falar(); unmount();
    await act(async () => resolver('Tarde')); expect(mocks.enviar).not.toHaveBeenCalled();
  });
});
