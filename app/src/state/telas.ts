// Telas ao vivo (Vitral-6): último quadro do navegador (`navegador.tela`) e do computador (`computador.tela`)
// de cada bot. Os eventos chegam pelo SSE global; `state/equipe.ts` repassa para cá (como faz com a memória).
// O texto digitado pelo usuário nunca passa por este estado.
import { useSyncExternalStore } from 'react';

export interface QuadroNavegador { abaId: string; agenteId: string; url: string; titulo: string; largura: number; altura: number; imagem: string | null; recebidoEm: number; aviso: string | null }
export interface QuadroComputador { agenteId: string; alvo: string; ligado: boolean; geracao: number; largura: number; altura: number; imagem: string | null; janelaAtiva: string | null; acao: string | null; mudou: boolean | null; recebidoEm: number }
export interface EstadoTelas { navegador: Record<string, QuadroNavegador>; computador: Record<string, QuadroComputador> }
export const telasIniciais = (): EstadoTelas => ({ navegador: {}, computador: {} });

type Dados = Record<string, unknown>;
const txt = (v: unknown) => typeof v === 'string' ? v : '';
const txtOuNulo = (v: unknown) => typeof v === 'string' && v ? v : null;
const num = (v: unknown) => typeof v === 'number' && Number.isFinite(v) ? v : 0;
const imagemValida = (v: unknown) => typeof v === 'string' && v.startsWith('data:image/') ? v : null;

/** Redutor puro. Quadro sem `miniatura` (igual ao anterior) mantém a imagem que já existe; geração antiga é ignorada. */
export function aplicarEventoTelas(e: EstadoTelas, tipo: string, d: Dados, agora = Date.now()): EstadoTelas {
  if (tipo === 'navegador.tela') {
    const agenteId = txt(d.agente_id), abaId = txt(d.aba_id); if (!agenteId || !abaId) return e;
    const antes = e.navegador[agenteId]; const mesmaAba = antes?.abaId === abaId;
    const imagem = imagemValida(d.miniatura) ?? (mesmaAba ? antes.imagem : null);
    return { ...e, navegador: { ...e.navegador, [agenteId]: { abaId, agenteId, url: txt(d.url), titulo: txt(d.titulo), largura: num(d.largura) || antes?.largura || 0, altura: num(d.altura) || antes?.altura || 0, imagem, recebidoEm: agora, aviso: txtOuNulo(d.aviso) } } };
  }
  if (tipo === 'computador.tela') {
    const agenteId = txt(d.agente_id); if (!agenteId) return e;
    const antes = e.computador[agenteId]; const geracao = num(d.geracao);
    if (antes && geracao < antes.geracao) return e;
    const ligado = d.ligado === true;
    const imagem = ligado ? (imagemValida(d.miniatura) ?? antes?.imagem ?? null) : null;
    return { ...e, computador: { ...e.computador, [agenteId]: { agenteId, alvo: txt(d.alvo) || 'virtual', ligado, geracao, largura: num(d.largura) || antes?.largura || 0, altura: num(d.altura) || antes?.altura || 0, imagem, janelaAtiva: txtOuNulo(d.janela_ativa), acao: txtOuNulo(d.acao), mudou: typeof d.mudou === 'boolean' ? d.mudou : null, recebidoEm: agora } } };
  }
  return e;
}

let estado = telasIniciais();
const ouvintes = new Set<() => void>();
export const lerTelas = () => estado;
export function useTelas() { return useSyncExternalStore(fn => { ouvintes.add(fn); return () => { ouvintes.delete(fn); }; }, lerTelas, lerTelas); }
export function receberEventoTelas(ev: { tipo: string; dados: Dados }) {
  const p = aplicarEventoTelas(estado, ev.tipo, ev.dados); if (p !== estado) { estado = p; ouvintes.forEach(f => f()); }
}
/** Esquece o quadro de um bot (a aba fechou ou o computador desligou). */
export function limparTelaNavegador(agenteId: string, abaId?: string) {
  if (!estado.navegador[agenteId] || (abaId && estado.navegador[agenteId].abaId !== abaId)) return;
  const { [agenteId]: _, ...resto } = estado.navegador; estado = { ...estado, navegador: resto }; ouvintes.forEach(f => f());
}
export function reiniciarTelas() { estado = telasIniciais(); ouvintes.forEach(f => f()); }
