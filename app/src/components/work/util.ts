import { PLUGIN_ICONS } from '../../data/pluginIcons';

/** Ícone/cor de um plugin pelo nome (ex.: "Figma"). */
export const pluginInfo = (nome?: string) => PLUGIN_ICONS.find(p => p.name === nome);

/** Duração legível em PT-BR: 2400 → "2,4 s". */
export const duracao = (ms: number) => `${(ms / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 1, minimumFractionDigits: ms < 10000 ? 1 : 0 })} s`;
