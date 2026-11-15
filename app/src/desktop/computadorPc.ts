// C3 (Vela-3): o app de desktop como ponte entre o servidor e o PC do usuário.
//
// Só na janela principal do desktop e só com alguém logado. O servidor nunca age no PC: aqui o
// app se apresenta (POST /v1/computador-pc/sessao), busca os comandos por long-poll autenticado
// (GET …/comandos), manda cada um para o Rust (pcExecutar, que confere tudo de novo) e devolve o
// resultado (POST …/comandos/{id}/resultado: id, prazo e uso único ficam no servidor).
// Parar na borda vira POST …/parar. A captura e o texto digitado não ficam guardados no app.
import { useSyncExternalStore } from 'react';
import { api, buscarAutenticado, ehErroApi, mensagemDeErro } from '../api/cliente';
import {
  aoPcEstado, aoPcParar, janelaAtual, noDesktop, pcAutorizar, pcConta, pcEstado, pcExecutar, pcSair,
  type ComandoPc, type EstadoPcLocal,
} from './ponte';

export interface SessaoPc { sessao_id: string; usuario_id: string; autorizados: string[]; validade_s: number }

export interface EstadoPontePc {
  /** Esta janela pode controlar o PC (app de desktop, janela principal). */
  disponivel: boolean;
  conectado: boolean;
  sessaoId: string | null;
  /** Outro computador entrou nesta conta e assumiu o controle. */
  substituida: boolean;
  erro: string | null;
  local: EstadoPcLocal | null;
}

const INICIAL: EstadoPontePc = {
  disponivel: noDesktop && janelaAtual === 'main',
  conectado: false,
  sessaoId: null,
  substituida: false,
  erro: null,
  local: null,
};

let estado: EstadoPontePc = INICIAL;
const ouvintes = new Set<() => void>();

function definir(parcial: Partial<EstadoPontePc>): void {
  estado = { ...estado, ...parcial };
  ouvintes.forEach(o => o());
}

export const lerPontePc = (): EstadoPontePc => estado;

export function usePontePc(): EstadoPontePc {
  return useSyncExternalStore(
    cb => { ouvintes.add(cb); return () => { ouvintes.delete(cb); }; },
    lerPontePc,
    lerPontePc,
  );
}

const esperar = (ms: number, sinal: AbortSignal) => new Promise<void>(resolve => {
  const t = window.setTimeout(resolve, ms);
  sinal.addEventListener('abort', () => { window.clearTimeout(t); resolve(); }, { once: true });
});

const DISPOSITIVO = 'App de desktop da Sora (Windows)';

let reiniciar: (() => void) | null = null;

/** Liga a ponte (enquanto houver sessão logada). Devolve a função que desliga. */
export function iniciarPontePc(): () => void {
  if (!INICIAL.disponivel) return () => {};
  const controle = new AbortController();
  const sinal = controle.signal;
  let sessaoId: string | null = null;

  const pararNoServidor = (agenteId: string) => {
    if (sessaoId) void api.post('/v1/computador-pc/parar', { sessao_id: sessaoId, agente_id: agenteId }).catch(() => {});
  };
  const pararEvento = aoPcParar(pararNoServidor);
  const pararEstado = aoPcEstado(local => {
    const novaPausa = local.pausado && (!estado.local?.pausado || estado.local.controlando?.id !== local.controlando?.id);
    definir({ local });
    if (novaPausa && sessaoId && local.controlando) {
      void api.post('/v1/computador-pc/pausar', { sessao_id: sessaoId, agente_id: local.controlando.id }).catch(() => {});
    }
  });

  async function laco(id: string): Promise<'substituida' | 'fim'> {
    while (!sinal.aborted) {
      let resposta: Response;
      try {
        resposta = await buscarAutenticado(`/v1/computador-pc/comandos?sessao_id=${encodeURIComponent(id)}&espera=20`, { signal: sinal });
      } catch (e) {
        if (sinal.aborted) return 'fim';
        if (ehErroApi(e) && e.status === 409) return 'substituida';
        throw e;
      }
      if (resposta.status === 204) continue;
      const comando = await resposta.json() as ComandoPc;
      if (sinal.aborted) return 'fim';
      let saida;
      try {
        saida = await pcExecutar(comando);
      } catch (e) {
        saida = { ok: false, erro: { codigo: 'falha', mensagem: String(e).slice(0, 300) } };
      }
      // o resultado pode chegar depois do prazo (409): o servidor já desistiu desse comando
      await api.post(`/v1/computador-pc/comandos/${encodeURIComponent(comando.id)}/resultado`, { sessao_id: id, ...saida }).catch(() => {});
    }
    return 'fim';
  }

  async function rodar(): Promise<void> {
    let espera = 2000;
    while (!sinal.aborted) {
      try {
        const sessao = await api.post<SessaoPc>('/v1/computador-pc/sessao', { dispositivo: DISPOSITIVO, autorizados: [] }, { signal: sinal });
        if (sinal.aborted) { void api.delete(`/v1/computador-pc/sessao/${sessao.sessao_id}`).catch(() => {}); return; }
        sessaoId = sessao.sessao_id;
        const local = await pcConta(sessao.usuario_id);
        if (local?.autorizados.length) {
          await api.put(`/v1/computador-pc/sessao/${sessao.sessao_id}`, { autorizados: local.autorizados }, { signal: sinal });
        }
        definir({ conectado: true, sessaoId, substituida: false, erro: null, local });
        espera = 2000;
        if (await laco(sessao.sessao_id) === 'substituida') {
          sessaoId = null;
          definir({ conectado: false, sessaoId: null, substituida: true });
          void pcSair().catch(() => {});
          return; // outro PC assumiu: não brigar por ele (Configurações → Reconectar)
        }
      } catch (e) {
        if (sinal.aborted) return;
        void pcSair().catch(() => {});
        sessaoId = null;
        definir({ conectado: false, sessaoId: null, erro: mensagemDeErro(e) });
        await esperar(espera, sinal);
        espera = Math.min(espera * 2, 30_000);
      }
    }
  }

  void rodar();
  return () => {
    controle.abort();
    pararEvento();
    pararEstado();
    void pcSair().catch(() => {});
    if (sessaoId) void api.delete(`/v1/computador-pc/sessao/${sessaoId}`).catch(() => {});
    sessaoId = null;
    definir({ conectado: false, sessaoId: null });
  };
}

/** Componente-dono chama ao montar: liga a ponte e permite "Reconectar" pela tela. */
export function ligarPontePc(): () => void {
  let parar = iniciarPontePc();
  reiniciar = () => { parar(); parar = iniciarPontePc(); };
  void pcEstado().then(local => { if (local) definir({ local }); }).catch(() => {});
  return () => { reiniciar = null; parar(); };
}

/** Outro computador assumiu e o usuário quer este de volta. */
export function reconectarPontePc(): void {
  definir({ substituida: false, erro: null });
  reiniciar?.();
}

/** Liga/desliga um bot neste PC e avisa o servidor (que só pede ao app para bots ligados). */
export async function alternarBotNoPc(agenteId: string, ligado: boolean): Promise<void> {
  const local = await pcAutorizar(agenteId, ligado);
  if (!local) return;
  definir({ local });
  const id = estado.sessaoId;
  if (id) await api.put(`/v1/computador-pc/sessao/${id}`, { autorizados: local.autorizados });
}

/** Só para testes. */
export function _reiniciarPontePcParaTestes(): void {
  estado = INICIAL;
  reiniciar = null;
}
