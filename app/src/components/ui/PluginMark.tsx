import type { CSSProperties } from 'react';

const logoFiles: Record<string, string> = {
  Higgsfield: 'higgsfield', ChatGPT: 'chatgpt', Canva: 'canva', Slack: 'slack',
  LinkedIn: 'linkedin', Runway: 'runway', Salesforce: 'salesforce', Midjourney: 'midjourney',
};

function luminance(hex: string) {
  const value = hex.replace('#', '');
  if (!/^[0-9a-f]{6}$/i.test(value)) return 1;
  const channels = [0, 2, 4].map((offset) => Number.parseInt(value.slice(offset, offset + 2), 16) / 255)
    .map((channel) => channel <= .03928 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4);
  return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2];
}

export function PluginMark({ nome, cor, path, size = 28 }: { nome: string; cor: string; path: string | null; size?: number }) {
  const dark = luminance(cor) < .16;
  const displayColor = dark ? '#F2F5FB' : cor;
  const style = { '--plugin-color': displayColor, width: size, height: size } as CSSProperties;
  const file = logoFiles[nome];
  if (file) return <img className={`plugin-mark ${dark ? 'plugin-mark-dark' : ''}`} src={`/logos/${file}.png`} alt="" style={style} />;
  if (path) return <svg className="plugin-mark" viewBox="0 0 24 24" aria-hidden="true" style={style}><path d={path} fill={displayColor} /></svg>;
  return <span className="plugin-mark plugin-fallback" style={style}>{nome.slice(0, 1)}</span>;
}

