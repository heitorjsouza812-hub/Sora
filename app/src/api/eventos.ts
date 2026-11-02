import { buscarAutenticado, ErroApi } from './cliente';

export interface EventoSse<T = Record<string, unknown>> {
  id: string;
  tipo: string;
  dados: T;
  recebidoEm: number;
}

export interface OpcoesEventos {
  signal: AbortSignal;
  ultimoId?: string;
  aoEvento: (evento: EventoSse) => void;
  aoErro?: (erro: unknown) => void;
}

function separarEventos(buffer: string): { blocos: string[]; resto: string } {
  const normalizado = buffer.replace(/\r\n/g, '\n');
  const partes = normalizado.split('\n\n');
  return { blocos: partes.slice(0, -1), resto: partes.at(-1) ?? '' };
}

function decodificar(bloco: string): Omit<EventoSse, 'recebidoEm'> | null {
  let id = '';
  let tipo = 'message';
  const dados: string[] = [];
  for (const linha of bloco.split('\n')) {
    if (!linha || linha.startsWith(':')) continue;
    const pos = linha.indexOf(':');
    const campo = pos < 0 ? linha : linha.slice(0, pos);
    const valor = pos < 0 ? '' : linha.slice(pos + 1).replace(/^ /, '');
    if (campo === 'id') id = valor;
    else if (campo === 'event') tipo = valor;
    else if (campo === 'data') dados.push(valor);
  }
  if (!dados.length && tipo === 'message') return null;
  const texto = dados.join('\n') || '{}';
  return { id, tipo, dados: JSON.parse(texto) as Record<string, unknown> };
}

/** O id do Redis Stream é `<ms>-<seq>`: o relógio do servidor mantém a ordem estável ao reabrir a conversa. */
export function horarioDoEvento(id: string): number {
  const ms = /^(\d{10,})-\d+$/.exec(id)?.[1];
  return ms ? Number(ms) : Date.now();
}

const esperar = (ms: number, signal: AbortSignal) => new Promise<void>((resolve, reject) => {
  const timer = window.setTimeout(resolve, ms);
  signal.addEventListener('abort', () => { window.clearTimeout(timer); reject(signal.reason); }, { once: true });
});

/** Consome SSE autenticado e retoma pelo último id confirmado. Só termina quando o sinal é abortado. */
export async function acompanharEventos(caminho: string, opcoes: OpcoesEventos): Promise<void> {
  let ultimoId = opcoes.ultimoId ?? '0-0';
  let tentativa = 0;
  while (!opcoes.signal.aborted) {
    try {
      const resposta = await buscarAutenticado(caminho, {
        headers: { Accept: 'text/event-stream', 'Last-Event-ID': ultimoId },
        signal: opcoes.signal,
      });
      if (!resposta.body) throw new Error('O servidor não abriu o canal de eventos.');
      tentativa = 0;
      const leitor = resposta.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (!opcoes.signal.aborted) {
        const { value, done } = await leitor.read();
        buffer += decoder.decode(value, { stream: !done });
        const { blocos, resto } = separarEventos(buffer);
        buffer = resto;
        for (const bloco of blocos) {
          const evento = decodificar(bloco);
          if (!evento) continue;
          if (evento.id) ultimoId = evento.id;
          if (evento.tipo !== 'ping') opcoes.aoEvento({ ...evento, recebidoEm: horarioDoEvento(evento.id) });
        }
        if (done) break;
      }
    } catch (erro) {
      if (opcoes.signal.aborted) return;
      // 400 = Last-Event-ID fora do formato `ms-seq`: recomeça do histórico retido, uma vez; o redutor é
      // idempotente. Se ainda assim der 400, vira erro comum e segue o recuo (sem laço apertado).
      if (erro instanceof ErroApi && erro.status === 400 && ultimoId !== '0-0') { ultimoId = '0-0'; continue; }
      opcoes.aoErro?.(erro);
    }
    tentativa += 1;
    await esperar(Math.min(1000 * 2 ** Math.min(tentativa, 4), 15_000), opcoes.signal).catch(() => undefined);
  }
}
