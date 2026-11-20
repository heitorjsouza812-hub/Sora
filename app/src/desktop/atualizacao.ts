// Atualização automática do app de desktop (Onda 1, 2026-11-20).
// Procura versão nova 15 s depois de abrir e a cada 6 h. Achou: aviso com "Instalar e reiniciar"
// (uma vez por versão). Tudo também à mão em Configurações → Conta → Versão do app.
// No navegador e na janela da Ilha nada disso roda.
import { useSyncExternalStore } from 'react';
import { toast } from '../components/base';
import { instalarAtualizacao, janelaAtual, noDesktop, verificarAtualizacao, type VerificacaoAtualizacao } from './ponte';

const PRIMEIRA_VERIFICACAO_MS = 15_000;
const INTERVALO_MS = 6 * 60 * 60 * 1000;

export type EstadoAtualizacao =
  | { fase: 'parada'; ultima: VerificacaoAtualizacao | null; erro?: string }
  | { fase: 'verificando' | 'instalando'; ultima: VerificacaoAtualizacao | null };

let estado: EstadoAtualizacao = { fase: 'parada', ultima: null };
const ouvintes = new Set<() => void>();
let avisada: string | null = null;

function definir(novo: EstadoAtualizacao): void { estado = novo; for (const cb of [...ouvintes]) cb(); }
const assinar = (cb: () => void) => { ouvintes.add(cb); return () => { ouvintes.delete(cb); }; };
export function useAtualizacao(): EstadoAtualizacao { return useSyncExternalStore(assinar, () => estado, () => estado); }

/** O app tem como se atualizar aqui? (desktop, janela principal) */
export const atualizacaoPossivel = (): boolean => noDesktop && janelaAtual === 'main';

export async function procurarAtualizacao(): Promise<VerificacaoAtualizacao | null> {
  if (!atualizacaoPossivel() || estado.fase !== 'parada') return estado.ultima;
  definir({ fase: 'verificando', ultima: estado.ultima });
  try {
    const ultima = await verificarAtualizacao();
    definir({ fase: 'parada', ultima });
    return ultima;
  } catch (erro) {
    definir({ fase: 'parada', ultima: estado.ultima, erro: typeof erro === 'string' ? erro : 'Não consegui verificar a atualização agora.' });
    return null;
  }
}

export async function instalarAgora(): Promise<void> {
  if (!atualizacaoPossivel() || estado.fase !== 'parada') return;
  definir({ fase: 'instalando', ultima: estado.ultima });
  try {
    await instalarAtualizacao(); // em sucesso o app fecha ou reinicia antes de voltar aqui
    definir({ fase: 'parada', ultima: estado.ultima });
  } catch (erro) {
    const mensagem = typeof erro === 'string' ? erro : 'Não consegui instalar a atualização.';
    definir({ fase: 'parada', ultima: estado.ultima, erro: mensagem });
    toast({ mensagem, tom: 'erro' });
  }
}

async function verificarEAvisar(): Promise<void> {
  const resultado = await procurarAtualizacao();
  if (resultado?.estado !== 'disponivel' || avisada === resultado.versao_nova) return;
  avisada = resultado.versao_nova;
  toast({
    mensagem: `A versão ${resultado.versao_nova} da Sora está pronta.`,
    tom: 'neutro',
    duracao: 20_000,
    acao: { rotulo: 'Instalar e reiniciar', onClick: () => { void instalarAgora(); } },
  });
}

let iniciada = false;

/** Liga a verificação periódica (uma vez por app, só na janela principal do desktop). */
export function iniciarVerificacaoDeAtualizacao(): void {
  if (iniciada || !atualizacaoPossivel()) return;
  iniciada = true;
  setTimeout(() => { void verificarEAvisar(); }, PRIMEIRA_VERIFICACAO_MS);
  setInterval(() => { void verificarEAvisar(); }, INTERVALO_MS);
}

/** Só para testes. */
export function _reiniciarAtualizacaoParaTestes(): void { estado = { fase: 'parada', ultima: null }; avisada = null; iniciada = false; }
