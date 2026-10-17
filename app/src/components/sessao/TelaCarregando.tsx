import { SoraOrb } from '../mascot';

/** Carregando = a Sora pensando (sem spinner). */
export function TelaCarregando() {
  return <main className="orb-route-loading"><SoraOrb size={96} state="thinking" title="Carregando" /></main>;
}
