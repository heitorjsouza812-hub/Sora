import type { Agente, Entrega, Plano, Plugin, Usuario } from '../types';
import { PLUGIN_ICONS } from './pluginIcons';

export const PEDIDO_CAMPANHA = 'Crie uma campanha para lançar minha cafeteria: pesquise referências, prepare as peças e monte um calendário de posts.';
export const PEDIDO_AJUSTE = 'Deixe os textos mais descontraídos.';

export const usuario: Usuario = {
  id: 'cafeteria-aroma',
  nome: 'Cafeteria Aroma',
  empresa: 'Cafeteria Aroma',
  plano: 'Plano Pro',
};

export const agentes: Agente[] = [
  {
    id: 'atlas', projetoId: 'campanha-cafeteria', nome: 'Atlas',
    funcao: 'Pesquisa e referências', cor: '#56A8FF', tipoMovimento: 'vibracao',
    ferramentas: ['Perplexity', 'Google Drive', 'Notion'], status: 'aguardando',
    verbo: 'Pesquisando', espera: 'Aguardando',
  },
  {
    id: 'luna', projetoId: 'campanha-cafeteria', nome: 'Luna',
    funcao: 'Criação visual', cor: '#AC80FF', tipoMovimento: 'espiral',
    ferramentas: ['Higgsfield', 'Figma', 'Canva'], status: 'aguardando',
    verbo: 'Criando', espera: 'Aguardando referências',
  },
  {
    id: 'nina', projetoId: 'campanha-cafeteria', nome: 'Nina',
    funcao: 'Textos e planejamento', cor: '#46E8A8', tipoMovimento: 'ondas',
    ferramentas: ['Notion', 'Google Agenda', 'Instagram'], status: 'aguardando',
    verbo: 'Escrevendo', espera: 'Aguardando peças',
  },
];

export const plano: Plano = {
  id: 'plano-campanha',
  projetoId: 'campanha-cafeteria',
  tarefas: [
    { id: 'pesquisa', planoId: 'plano-campanha', titulo: 'Pesquisar referências', ordem: 1, dependeDe: [], agenteId: 'atlas', status: 'aguardando', progresso: 0 },
    { id: 'pecas', planoId: 'plano-campanha', titulo: 'Criar peças', ordem: 2, dependeDe: ['pesquisa'], agenteId: 'luna', status: 'aguardando', progresso: 0 },
    { id: 'calendario', planoId: 'plano-campanha', titulo: 'Organizar calendário', ordem: 3, dependeDe: ['pecas'], agenteId: 'nina', status: 'aguardando', progresso: 0 },
  ],
};

export const referencias = [
  { titulo: 'Branding de cafeterias independentes', dominio: 'behance.net', url: 'https://www.behance.net/search/projects/cafe%20branding', imagem: '/campanha/post.jpg' },
  { titulo: 'Moodboard: café e aconchego', dominio: 'pinterest.com', url: 'https://www.pinterest.com/search/pins/?q=cozy%20coffee%20shop', imagem: '/campanha/story.jpg' },
  { titulo: 'Campanhas de inauguração', dominio: 'instagram.com', url: 'https://www.instagram.com/explore/tags/cafeteria/', imagem: '/campanha/post.jpg' },
  { titulo: 'Paletas e tipografia para cafés', dominio: 'canva.com', url: 'https://www.canva.com/templates/search/coffee/', imagem: '/campanha/story.jpg' },
];

export const pecas = [
  { titulo: 'Post de inauguração', formato: '1080 × 1080', imagem: '/campanha/post.jpg' },
  { titulo: 'Story', formato: '1080 × 1920', imagem: '/campanha/story.jpg' },
  { titulo: 'Cartaz da vitrine', formato: 'A3', imagem: '/campanha/post.jpg' },
];

export const legendaAnterior = 'Abrimos as portas! Venha provar nosso café especial na inauguração, sábado às 9h.';
export const legendaNova = 'Chegou o café que abraça! Bora estrear nossa cafeteria? Sábado, 9h, com cheirinho de café fresquinho.';

export const calendario = [
  { dia: 2, tipo: 'Post' }, { dia: 4, tipo: 'Story' }, { dia: 6, tipo: 'Reels' },
  { dia: 7, tipo: 'Post' }, { dia: 9, tipo: 'Story' }, { dia: 11, tipo: 'Post' },
  { dia: 13, tipo: 'Reels' }, { dia: 16, tipo: 'Post' }, { dia: 18, tipo: 'Story' },
  { dia: 20, tipo: 'Post' }, { dia: 23, tipo: 'Reels' }, { dia: 27, tipo: 'Post' },
];

export const entregas: Entrega[] = [
  { id: 'entrega-pesquisa', tarefaId: 'pesquisa', agenteId: 'atlas', tipo: 'links', conteudo: referencias, versao: 1 },
  { id: 'entrega-pecas', tarefaId: 'pecas', agenteId: 'luna', tipo: 'imagem', conteudo: pecas, versao: 1 },
  { id: 'entrega-calendario', tarefaId: 'calendario', agenteId: 'nina', tipo: 'calendario', conteudo: calendario, versao: 1 },
];

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

