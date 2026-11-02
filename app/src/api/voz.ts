// Voz com a chave do próprio usuário (Relógio): POST /v1/voz/transcrever e /v1/voz/falar.
// 404 = o usuário não conectou um provedor de voz; a tela mostra o aviso em PT-BR em vez de falhar.
import { buscarAutenticado, ehErroApi, ErroApi } from './cliente';

export const MSG_SEM_VOZ = 'Para usar a voz, conecte uma chave da OpenAI em Configurações → Modelos de IA.';
const MSG_VAZIO = 'Não ouvi nada. Tente falar de novo.';
const MSG_GRANDE = 'O áudio ficou grande demais. Fale um trecho mais curto.';
const MSG_PROVEDOR = 'O provedor de voz não conseguiu responder agora. Tente de novo.';

/** Troca as mensagens do servidor por avisos próprios do app; o que não conhecemos passa como veio. */
function erroDeVoz(e: unknown): unknown {
  if (!ehErroApi(e)) return e;
  const texto = e.status === 404 ? MSG_SEM_VOZ : e.status === 413 ? MSG_GRANDE : e.status === 422 ? MSG_VAZIO : e.status === 502 ? MSG_PROVEDOR : null;
  return texto ? new ErroApi(e.status, texto) : e;
}

export async function transcreverAudio(audio: Blob, idioma = 'pt', signal?: AbortSignal): Promise<string> {
  const corpo = new FormData();
  corpo.append('audio', audio, audio.type.includes('mp4') ? 'fala.m4a' : 'fala.webm');
  corpo.append('idioma', idioma);
  try {
    const resposta = await buscarAutenticado('/v1/voz/transcrever', { method: 'POST', body: corpo, signal });
    const { texto } = await resposta.json() as { texto: string };
    return texto.trim();
  } catch (e) { throw erroDeVoz(e); }
}

export async function sintetizarFala(texto: string, signal?: AbortSignal): Promise<Blob> {
  try {
    const resposta = await buscarAutenticado('/v1/voz/falar', { method: 'POST', body: JSON.stringify({ texto }), headers: { 'Content-Type': 'application/json' }, signal });
    return await resposta.blob();
  } catch (e) { throw erroDeVoz(e); }
}

let tocando: { audio: HTMLAudioElement; url: string } | null = null;
export function pararFala() { if (tocando) { tocando.audio.pause(); URL.revokeObjectURL(tocando.url); tocando = null; } }

/** Fala o texto e toca; uma fala por vez. Resolve quando termina de tocar. */
export async function ouvirTexto(texto: string): Promise<void> {
  pararFala();
  const url = URL.createObjectURL(await sintetizarFala(texto));
  const audio = new Audio(url);
  tocando = { audio, url };
  await new Promise<void>((resolve, reject) => {
    audio.onended = () => resolve();
    audio.onerror = () => reject(new Error('Não foi possível tocar o áudio.'));
    audio.play().catch(reject);
  }).finally(() => { if (tocando?.audio === audio) pararFala(); });
}
