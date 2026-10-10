import { PLUGIN_ICONS } from '../../data/pluginIcons';
import type { DefinicaoProvedor } from '../../state/modelos';

export function ProviderIcon({ provedor }: { provedor: DefinicaoProvedor }) {
  const icon = PLUGIN_ICONS.find(item => item.name === provedor.iconePlugin);
  const letras = provedor.nome.split(/\s+/).map(x => x[0]).join('').slice(0, 2).toUpperCase();
  return <span className="cfg-provider-icon" style={{ '--provider-color': icon?.hex ?? '#8fa8d8' } as React.CSSProperties} aria-hidden="true">
    {icon?.path ? <svg viewBox="0 0 24 24"><path d={icon.path} /></svg> : letras}
  </span>;
}

