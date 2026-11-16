import type { ReactNode } from 'react';
import type { ProvedorModeloId } from '../../state/modelos';

/** Marca própria de cada provedor: forma geométrica simples, cor e letra que lembram o provedor. Não copia logotipo. */
const FORMAS: Record<ProvedorModeloId | 'auto', { cor: string; forma: ReactNode }> = {
  openai: { cor: '#3DDBA5', forma: <><circle cx="12" cy="12" r="6.2" /><circle cx="12" cy="12" r="2.2" /></> },
  anthropic: { cor: '#E8946A', forma: <path d="M12 4.5 19 19.5h-3.2L12 11.2 8.2 19.5H5z" /> },
  gemini: { cor: '#7FA8FF', forma: <path d="M12 3c.6 5.2 3.8 8.4 9 9-5.2.6-8.4 3.8-9 9-.6-5.2-3.8-8.4-9-9 5.2-.6 8.4-3.8 9-9z" /> },
  groq: { cor: '#FF7A59', forma: <path d="M15.8 8.2a5 5 0 1 0 0 7.6V12h-3.6" /> },
  openrouter: { cor: '#8F9CFF', forma: <path d="M4 8h10m0 0-3-3m3 3-3 3M20 16H10m0 0 3-3m-3 3 3 3" /> },
  ollama: { cor: '#D6DCE8', forma: <><circle cx="12" cy="13" r="6" /><path d="M8.2 8.2 7.4 4.5m8.4 3.7.8-3.7" /></> },
  xai: { cor: '#EEF2FA', forma: <path d="m5 5 14 14M19 5 5 19" /> },
  deepseek: { cor: '#5C8DFF', forma: <path d="M4 14c3-6 8-7 16-4-2 5-6 8-11 8-1.8 0-3.5-1.4-5-4zM15.5 11.5h.01" /> },
  mistral: { cor: '#FFB547', forma: <path d="M5 5h3.5v3.5H5zM15.5 5H19v3.5h-3.5zM5 10.3h14v3.4H5zM5 15.5h3.5V19H5zM15.5 15.5H19V19h-3.5z" /> },
  'openai-compativel': { cor: '#A9B3C6', forma: <path d="M8.5 7 4 12l4.5 5M15.5 7 20 12l-4.5 5" /> },
  auto: { cor: '#E2ECFF', forma: <path d="M12 3.5 13.8 10 20.5 12 13.8 14 12 20.5 10.2 14 3.5 12 10.2 10z" /> },
};

export function IconeProvedor({ id, tamanho = 18 }: { id: ProvedorModeloId | 'auto'; tamanho?: number }) {
  const { cor, forma } = FORMAS[id] ?? FORMAS['openai-compativel'];
  return <svg className="icone-provedor" data-provedor={id} width={tamanho} height={tamanho} viewBox="0 0 24 24" aria-hidden="true" focusable="false"
    fill={['anthropic', 'gemini', 'mistral', 'auto'].includes(id) ? cor : 'none'} stroke={cor} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{forma}</svg>;
}
