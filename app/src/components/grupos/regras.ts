export const MIN_BOTS = 2;
export const MAX_BOTS = 5;

/** O que falta para o botão deixar de estar desativado (vazio quando está tudo certo). */
export const faltaParaOGrupo = (marcados: number) => marcados < MIN_BOTS ? `Escolha pelo menos ${MIN_BOTS} bots` : '';
