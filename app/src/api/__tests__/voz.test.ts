import { afterEach, describe, expect, it, vi } from 'vitest';

const buscarAutenticado = vi.hoisted(() => vi.fn());
vi.mock('../cliente', async (importar) => ({ ...(await importar<typeof import('../cliente')>()), buscarAutenticado }));

import { ErroApi } from '../cliente';
import { MSG_SEM_VOZ, sintetizarFala, transcreverAudio } from '../voz';
afterEach(() => buscarAutenticado.mockReset());

describe('voz', () => {
  it('transcrever manda multipart com audio e idioma e devolve o texto', async () => {
    buscarAutenticado.mockResolvedValue({ json: async () => ({ texto: '  olá, Sora  ' }) });
    const texto = await transcreverAudio(new Blob(['x'], { type: 'audio/webm' }));
    expect(texto).toBe('olá, Sora');
    const [caminho, init] = buscarAutenticado.mock.calls[0];
    expect(caminho).toBe('/v1/voz/transcrever'); expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get('audio')).toBeInstanceOf(Blob);
    expect((init.body as FormData).get('idioma')).toBe('pt');
  });

  it('sem texto do servidor, 404, 413, 422 e 502 viram avisos próprios em PT-BR', async () => {
    for (const [status, trecho] of [[404, MSG_SEM_VOZ], [413, 'grande demais'], [422, 'Não ouvi nada'], [502, 'provedor de voz'], [424, 'recusou']] as const) {
      buscarAutenticado.mockRejectedValueOnce(new ErroApi(status, 'Algo deu errado'));
      await expect(transcreverAudio(new Blob(['x']))).rejects.toMatchObject({ status, mensagem: expect.stringContaining(trecho) });
    }
  });

  it('404, 424 e 502 mostram o motivo que o backend manda no detail', async () => {
    for (const [status, detalhe] of [
      [424, 'O administrador do Groq precisa aceitar os termos do modelo de voz no console do provedor.'],
      [404, 'O provedor conectado não tem modelo de fala.'],
      [502, 'A voz respondeu 400 ao falar.'],
    ] as const) {
      buscarAutenticado.mockRejectedValueOnce(new ErroApi(status, detalhe, { detalhe }));
      await expect(sintetizarFala('Olá')).rejects.toMatchObject({ status, mensagem: detalhe });
    }
  });

  it('falar manda o texto em JSON e devolve o áudio; 404 vira o mesmo aviso', async () => {
    buscarAutenticado.mockResolvedValueOnce({ blob: async () => new Blob(['mp3'], { type: 'audio/mpeg' }) });
    expect((await sintetizarFala('Olá')).type).toBe('audio/mpeg');
    expect(buscarAutenticado.mock.calls[0][1].body).toBe(JSON.stringify({ texto: 'Olá' }));
    buscarAutenticado.mockRejectedValueOnce(new ErroApi(404, 'Not Found'));
    await expect(sintetizarFala('Olá')).rejects.toMatchObject({ mensagem: MSG_SEM_VOZ });
  });
});
