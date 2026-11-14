// Rotina em linguagem de gente ("Todo dia às 09:00") ↔ o cron de 5 campos que o backend espera.
export type Frequencia = 'nenhuma' | 'diario' | 'uteis' | 'semanal' | 'personalizada';

export const FREQUENCIAS: { id: Exclude<Frequencia, 'personalizada'>; rotulo: string }[] = [
  { id: 'nenhuma', rotulo: 'Sem rotina' },
  { id: 'diario', rotulo: 'Todo dia' },
  { id: 'uteis', rotulo: 'Dias úteis' },
  { id: 'semanal', rotulo: 'Toda semana' },
];

export const DIAS_DA_SEMANA = ['Domingo', 'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado'] as const;

export interface RotinaAmigavel { frequencia: Frequencia; hora: string; dia: number }

const dois = (n: number) => String(n).padStart(2, '0');

/** Lê um cron simples (`M H * * *`, `M H * * 1-5`, `M H * * D`); qualquer outro vira "personalizada". */
export function lerAgendamento(cron: string | undefined | null): RotinaAmigavel {
  const padrao: RotinaAmigavel = { frequencia: 'nenhuma', hora: '09:00', dia: 1 };
  const texto = (cron ?? '').trim();
  if (!texto) return padrao;
  const m = /^(\d{1,2}) (\d{1,2}) \* \* (\*|1-5|[0-7])$/.exec(texto);
  if (!m || Number(m[1]) > 59 || Number(m[2]) > 23) return { ...padrao, frequencia: 'personalizada' };
  const hora = `${dois(Number(m[2]))}:${dois(Number(m[1]))}`;
  if (m[3] === '*') return { frequencia: 'diario', hora, dia: 1 };
  if (m[3] === '1-5') return { frequencia: 'uteis', hora, dia: 1 };
  return { frequencia: 'semanal', hora, dia: Number(m[3]) % 7 };
}

/** Monta o cron para o backend; `null` quando não há rotina ou a hora é inválida. */
export function montarAgendamento({ frequencia, hora, dia }: RotinaAmigavel): string | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(hora);
  if (!m || Number(m[1]) > 23 || Number(m[2]) > 59) return null;
  const base = `${Number(m[2])} ${Number(m[1])} * *`;
  if (frequencia === 'diario') return `${base} *`;
  if (frequencia === 'uteis') return `${base} 1-5`;
  if (frequencia === 'semanal') return `${base} ${dia}`;
  return null;
}
