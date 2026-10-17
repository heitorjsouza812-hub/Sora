// "Fazer isso depois": o onboarding some nesta aba do navegador (sessionStorage), mas o aviso fica na Home.
import { useSyncExternalStore } from 'react';

const CHAVE = 'sora.onboarding-pulado.v1';
let pulado = (() => { try { return sessionStorage.getItem(CHAVE) === '1'; } catch { return false; } })();
const ouvintes = new Set<() => void>();

export function pularOnboarding(): void {
  pulado = true;
  try { sessionStorage.setItem(CHAVE, '1'); } catch { /* sem storage: vale só em memória */ }
  for (const cb of [...ouvintes]) cb();
}

const assinar = (cb: () => void) => { ouvintes.add(cb); return () => { ouvintes.delete(cb); }; };
const ler = () => pulado;
export function useOnboardingPulado(): boolean { return useSyncExternalStore(assinar, ler, ler); }
