/** Texto novo que o bot propõe para as próprias instruções (`propor_instrucoes`), mostrado antes de aprovar. */
export interface PropostaInstrucoes { instrucoes: string; diferenca?: string; motivo?: string }

const texto = (v: unknown) => typeof v === 'string' ? v : '';

/** Lê o campo opcional `proposta` do evento `aprovacao.pedida` ou de `/v1/atencao`. */
export function propostaDe(v: unknown): PropostaInstrucoes | undefined {
  if (!v || typeof v !== 'object') return undefined;
  const d = v as Record<string, unknown>; const instrucoes = texto(d.instrucoes);
  if (!instrucoes) return undefined;
  return { instrucoes, ...(texto(d.diferenca) ? { diferenca: texto(d.diferenca) } : {}), ...(texto(d.motivo) ? { motivo: texto(d.motivo) } : {}) };
}
