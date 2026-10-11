// "Pop" + anel quando um agente conclui (CSS em ilha.css; some com prefers-reduced-motion).
import { useState } from 'react';
import type { AgenteIlha } from './ilhaEstado';

/** Anel na cor do agente que se expande uma vez quando ele conclui (não toca para quem já chegou concluído). */
export function AnelConclusao({ agente }: { agente: AgenteIlha }) {
  const [jaConcluido] = useState(() => agente.status === 'concluido');
  if (agente.status !== 'concluido' || jaConcluido) return null;
  return <span className="ilha-anel" aria-hidden="true" />;
}
