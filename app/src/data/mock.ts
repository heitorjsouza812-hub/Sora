// Catálogo da tela Plugins (congelada por decisão do grupo; os estados "Conectado" daqui não são reais).
// A conta de exemplo que morava aqui saiu: a conta vem da sessão (/v1/eu).
import type { Plugin } from '../types';
import { PLUGIN_ICONS } from './pluginIcons';

const destaques = new Map([
  ['Higgsfield', ['Imagens e vídeo com IA', false]],
  ['Figma', ['Design', true]],
  ['ChatGPT', ['Assistente de IA', true]],
  ['Gemini', ['Assistente de IA', true]],
  ['Canva', ['Design', true]],
  ['Notion', ['Documentos', true]],
]);

export const plugins: Array<Plugin & { destaque: boolean; descricao: string; cor: string; path: string | null }> = PLUGIN_ICONS.map((icone) => {
  const info = destaques.get(icone.name);
  return {
    id: icone.name.toLowerCase().replaceAll(' ', '-'), nome: icone.name,
    categoria: info?.[0] as string ?? 'Produtividade', conectado: Boolean(info?.[1]),
    destaque: Boolean(info), descricao: info?.[0] as string ?? 'Integração para agentes',
    cor: icone.hex, path: icone.path,
  };
});

