// Rolagem inteligente do chat: acompanha o fim SÓ se o usuário já estiver no fim. Se ele estiver
// lendo mais acima, nada pula; o botão "ir para o fim" aparece com o número de mensagens novas.
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type UIEvent } from 'react';

const PERTO = 80; // px do fim que ainda contam como "no fim"

/**
 * @param chaves  ids das mensagens/itens visíveis, em ordem (para contar as novas)
 * @param assinatura  muda quando o conteúdo cresce (ex.: texto em streaming) — mantém colado no fim
 */
export function useRolagemFim(chaves: string[], assinatura: string | number) {
  const ref = useRef<HTMLDivElement>(null);
  const noFimRef = useRef(true);
  const [noFim, setNoFim] = useState(true);
  const [vistas, setVistas] = useState<Set<string>>(() => new Set(chaves));

  const primeiro = useRef(chaves[0]);
  const altura = useRef(0);
  // no fim: acompanha o conteúdo novo (sem animação, para não "brigar" com o streaming)
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (primeiro.current && chaves[0] !== primeiro.current && chaves.includes(primeiro.current)) {
      el.scrollTop += el.scrollHeight - altura.current;
    } else if (noFimRef.current) el.scrollTop = el.scrollHeight;
    primeiro.current = chaves[0]; altura.current = el.scrollHeight;
  }, [chaves, assinatura]);

  // Markdown e imagens podem crescer depois do commit do texto (RAF / carregamento).
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => { if (noFimRef.current) el.scrollTop = el.scrollHeight; altura.current = el.scrollHeight; });
    for (const filho of Array.from(el.children)) observer.observe(filho);
    return () => observer.disconnect();
  }, [chaves.length]);

  const onScroll = useCallback((ev: UIEvent<HTMLElement>) => {
    const el = ev.currentTarget;
    const perto = el.scrollHeight - el.scrollTop - el.clientHeight < PERTO;
    if (perto === noFimRef.current) return;
    noFimRef.current = perto;
    setNoFim(perto);
    // ao sair do fim, tudo o que já está na tela conta como visto
    if (!perto) setVistas(new Set(Array.from(el.querySelectorAll<HTMLElement>('[data-chave]')).map(n => n.dataset.chave ?? '')));
  }, []);

  const irParaFim = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    noFimRef.current = true;
    setNoFim(true);
    const reduzir = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    el.scrollTo({ top: el.scrollHeight, behavior: reduzir ? 'auto' : 'smooth' });
  }, []);

  /** Força seguir o fim (ex.: quando o próprio usuário envia uma mensagem). */
  const seguirFim = useCallback(() => { noFimRef.current = true; setNoFim(true); }, []);

  const novas = noFim ? 0 : chaves.filter(k => !vistas.has(k)).length;
  return { ref, onScroll, noFim, novas, irParaFim, seguirFim };
}
