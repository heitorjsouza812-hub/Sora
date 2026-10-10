import type { CSSProperties } from 'react';

const logoFiles: Record<string, string> = {
  Higgsfield: 'higgsfield', ChatGPT: 'chatgpt', Canva: 'canva', Slack: 'slack',
  LinkedIn: 'linkedin', Runway: 'runway', Salesforce: 'salesforce', Midjourney: 'midjourney',
};

export function PluginMark({ nome, cor, path, size = 28 }: { nome: string; cor: string; path: string | null; size?: number }) {
  const style = { '--plugin-color': cor, width: size, height: size } as CSSProperties;
  const file = logoFiles[nome];
  if (file) return <img className="plugin-mark" src={`/logos/${file}.png`} alt="" style={style} />;
  if (path) return <svg className="plugin-mark" viewBox="0 0 24 24" aria-hidden="true" style={style}><path d={path} fill={cor} /></svg>;
  return <span className="plugin-mark plugin-fallback" style={style}>{nome.slice(0, 1)}</span>;
}

