// Presença: mantém por um instante os itens que saíram da lista (marcados `saindo`) para animar a saída.
import { useEffect, useState } from 'react';

const SAIDA_MS = 280;

/** Mantém por um instante os itens que saíram da lista, marcados como `saindo`, para animar a saída. */
export function usePresenca<T extends { id: string }>(itens: T[]): { item: T; saindo: boolean }[] {
  const chave = itens.map(i => i.id).join('|');
  const [anterior, setAnterior] = useState({ chave, itens });
  const [saindo, setSaindo] = useState<T[]>([]);

  // estado derivado das props (padrão do React): compara com a renderização anterior
  if (anterior.chave !== chave) {
    const ids = new Set(itens.map(i => i.id));
    const removidos = anterior.itens.filter(i => !ids.has(i.id));
    setAnterior({ chave, itens });
    setSaindo(s => [...s.filter(x => !ids.has(x.id) && !removidos.some(r => r.id === x.id)), ...removidos]);
  }

  useEffect(() => {
    if (!saindo.length) return;
    const t = window.setTimeout(() => setSaindo([]), SAIDA_MS);
    return () => window.clearTimeout(t);
  }, [saindo]);

  const ids = new Set(itens.map(i => i.id));
  return [
    ...itens.map(item => ({ item, saindo: false })),
    ...saindo.filter(x => !ids.has(x.id)).map(item => ({ item, saindo: true })),
  ];
}
