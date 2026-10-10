// Preferências do painel lateral: aba aberta e se está recolhido (localStorage, com try/catch).
import { useCallback, useEffect, useState } from 'react';

interface Preferencias { aba: string; recolhido: boolean }

function ler(chave: string, padrao: Preferencias): Preferencias {
  try {
    const bruto = localStorage.getItem(chave);
    return bruto ? { ...padrao, ...(JSON.parse(bruto) as Partial<Preferencias>) } : padrao;
  } catch { return padrao; }
}

/** Aba aberta + recolhido, lembrados entre visitas. */
export function usePainelLateral(chave: string, abaPadrao: string) {
  const [pref, setPref] = useState<Preferencias>(() => ler(chave, { aba: abaPadrao, recolhido: false }));
  useEffect(() => { try { localStorage.setItem(chave, JSON.stringify(pref)); } catch { /* sem armazenamento: só nesta visita */ } }, [chave, pref]);
  const setAba = useCallback((aba: string) => setPref((p) => ({ ...p, aba })), []);
  const setRecolhido = useCallback((recolhido: boolean) => setPref((p) => ({ ...p, recolhido })), []);
  return { aba: pref.aba, setAba, recolhido: pref.recolhido, setRecolhido };
}

