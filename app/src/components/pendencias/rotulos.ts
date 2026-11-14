export const ROTULOS_DECISAO = {
  permitirUmaVez: 'Permitir uma vez',
  semprePermitir: 'Sempre permitir',
  recusar: 'Recusar',
  enviar: 'Enviar',
  descartar: 'Descartar',
} as const;

/** O backend só grava "sempre permitir" para uma ferramenta real; domínio novo e mudança das
 *  próprias instruções ficam sempre com a decisão de cada vez. */
export function aceitaSempreLiberar(acao: string | null | undefined): boolean {
  return !!acao && acao !== 'aprovacao' && acao !== 'rascunho_envio' && acao !== 'propor_instrucoes';
}

export const COR_SORA_PEDIDO = '#E2ECFF';
