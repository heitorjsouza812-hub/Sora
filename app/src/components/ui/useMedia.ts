import { useSyncExternalStore } from 'react';

/** true enquanto a media query casar (ex.: '(max-width: 767px)'). */
export function useMedia(query: string) {
  return useSyncExternalStore(
    (f) => { const m = window.matchMedia(query); m.addEventListener('change', f); return () => m.removeEventListener('change', f); },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

export const useCelular = () => useMedia('(max-width: 767px)');
