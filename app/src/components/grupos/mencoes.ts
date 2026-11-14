import type { BotResumo } from '../../state/bots';

const semAcento = (valor: string) => valor.normalize('NFD').replace(/[̀-ͯ]/g, '').toLocaleLowerCase('pt-BR');
export const MENCAO_NO_FIM = /(?:^|\s)@([^\s]*)$/;

export interface OpcaoMencao { id: string; nome: string; cor?: string }

/** Opções de `@` para o trecho digitado: `@todos` (só os bots) e cada bot do grupo, filtrados pelo começo do nome. */
export function opcoesDeMencao(texto: string, bots: Pick<BotResumo, 'id' | 'nome' | 'cor'>[]): OpcaoMencao[] {
  const trecho = texto.match(MENCAO_NO_FIM)?.[1];
  if (trecho === undefined) return [];
  const alvo = semAcento(trecho);
  return [{ id: 'todos', nome: 'todos' }, ...bots].filter(opcao => semAcento(opcao.nome).startsWith(alvo));
}

/** Completa o `@trecho` do fim do texto. O backend lê a menção do começo do texto, então só o nome é inserido. */
export const completarMencao = (texto: string, nome: string) => texto.replace(MENCAO_NO_FIM, trecho => `${/^\s/.test(trecho) ? trecho[0] : ''}@${nome} `);
