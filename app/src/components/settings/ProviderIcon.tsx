import { PLUGIN_ICONS } from '../../data/pluginIcons';
import type { DefinicaoProvedor } from '../../state/modelos';

function iconeProprio(id: DefinicaoProvedor['id']) {
  if (id === 'openai') return <svg viewBox="0 0 24 24"><path d="M12 2.4a5 5 0 0 1 4.6 3 5 5 0 0 1 3.7 7.1 5 5 0 0 1-4.7 6.8A5 5 0 0 1 7 18.8a5 5 0 0 1-3.3-7.3A5 5 0 0 1 8.4 4.7 5 5 0 0 1 12 2.4Zm0 3.2-4.8 2.8v5.5l4.8 2.8 4.8-2.8V8.4L12 5.6Zm0 2.1 3 1.7v3.5l-3 1.7-3-1.7V9.4l3-1.7Z" /></svg>;
  if (id === 'mistral') return <svg viewBox="0 0 24 24"><path d="M3 3h4v4h2v2h2v6H9v2H7v4H3V3Zm14 0h4v18h-4v-4h-2v-2h-2V9h2V7h2V3ZM9 9h2v6H9V9Zm4 0h2v6h-2V9Z" /></svg>;
  if (id === 'openrouter') return <svg viewBox="0 0 24 24"><path d="M3 7h12V4l6 4.5-6 4.5v-3H3V7Zm18 10H9v3l-6-4.5L9 11v3h12v3Z" /></svg>;
  if (id === 'ollama') return <svg viewBox="0 0 24 24"><path d="M7 3h3v4h4V3h3v5c1.9 1 3 2.8 3 5v8H4v-8c0-2.2 1.1-4 3-5V3Zm1 8v7h8v-7h-2v2h-4v-2H8Zm2 4h1v1h-1v-1Zm3 0h1v1h-1v-1Z" /></svg>;
  if (id === 'xai') return <svg viewBox="0 0 24 24"><path d="m4 4 6.2 8L4 20h4.1l4.2-5.4 4.2 5.4H21l-6.4-8.2L20.7 4h-4.1l-4 5.2L8.5 4H4Z" /></svg>;
  return null;
}

export function ProviderIcon({ provedor }: { provedor: DefinicaoProvedor }) {
  const icon = PLUGIN_ICONS.find(item => item.name === provedor.iconePlugin);
  const letras = provedor.nome.split(/\s+/).map(x => x[0]).join('').slice(0, 2).toUpperCase();
  return <span className={`cfg-provider-icon cfg-provider-icon--${provedor.id}`} aria-hidden="true">
    {iconeProprio(provedor.id) ?? (icon?.path ? <svg viewBox="0 0 24 24"><path d={icon.path} /></svg> : letras)}
  </span>;
}

