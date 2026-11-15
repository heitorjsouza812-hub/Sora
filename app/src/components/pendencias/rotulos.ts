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

/** Linha que sobra depois da decisão ("✓ Permitido uma vez"). */
export const ROTULOS_RESOLVIDO: Record<string, string> = {
  aprovar: 'Permitido uma vez',
  sempre_permitir: 'Sempre permitido',
  recusar: 'Recusado',
  enviar: 'Enviado',
  descartar: 'Descartado',
  responder: 'Respondido',
};

/** "agora", "há 2 min", "há 3 h" ou a data; vazio quando não há hora. */
export function tempoRelativo(criadoEm?: number | null, agora = Date.now()): string {
  if (!criadoEm) return '';
  const min = Math.max(0, Math.floor((agora - criadoEm) / 60_000));
  if (min < 1) return 'agora';
  if (min < 60) return `há ${min} min`;
  if (min < 24 * 60) return `há ${Math.floor(min / 60)} h`;
  return new Date(criadoEm).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
}
