import { lerIlhaPrefs } from './ilhaEstado';

export type SomIlha = 'abrir' | 'concluiu' | 'pronto' | 'aprovado';

type AudioContextComWebkit = typeof AudioContext & { new(): AudioContext };

let contexto: AudioContext | null = null;

const notas: Record<SomIlha, { frequencia: number; atraso: number; duracao: number }[]> = {
  abrir: [{ frequencia: 440, atraso: 0, duracao: 0.08 }, { frequencia: 660, atraso: 0.055, duracao: 0.11 }],
  concluiu: [{ frequencia: 523, atraso: 0, duracao: 0.08 }, { frequencia: 784, atraso: 0.07, duracao: 0.13 }],
  pronto: [{ frequencia: 392, atraso: 0, duracao: 0.1 }, { frequencia: 523, atraso: 0.08, duracao: 0.1 }, { frequencia: 784, atraso: 0.16, duracao: 0.18 }],
  aprovado: [{ frequencia: 523, atraso: 0, duracao: 0.1 }, { frequencia: 659, atraso: 0.07, duracao: 0.1 }, { frequencia: 880, atraso: 0.14, duracao: 0.22 }],
};

function obterContexto(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  const Audio = window.AudioContext
    ?? (window as typeof window & { webkitAudioContext?: AudioContextComWebkit }).webkitAudioContext;
  if (!Audio) return null;
  contexto ??= new Audio();
  return contexto;
}

/** Toca uma assinatura curta e discreta, sem carregar arquivos externos. */
export function tocar(nome: SomIlha): void {
  if (!lerIlhaPrefs().som) return;
  const ctx = obterContexto();
  if (!ctx) return;
  if (ctx.state === 'suspended') void ctx.resume();
  const inicio = ctx.currentTime + 0.01;
  notas[nome].forEach(({ frequencia, atraso, duracao }) => {
    const oscilador = ctx.createOscillator();
    const ganho = ctx.createGain();
    oscilador.type = nome === 'abrir' ? 'sine' : 'triangle';
    oscilador.frequency.setValueAtTime(frequencia, inicio + atraso);
    ganho.gain.setValueAtTime(0.0001, inicio + atraso);
    ganho.gain.exponentialRampToValueAtTime(0.028, inicio + atraso + 0.012);
    ganho.gain.exponentialRampToValueAtTime(0.0001, inicio + atraso + duracao);
    oscilador.connect(ganho);
    ganho.connect(ctx.destination);
    oscilador.start(inicio + atraso);
    oscilador.stop(inicio + atraso + duracao + 0.02);
  });
}
