// Catálogo visual do construtor de agentes. O planejamento e a execução de pedidos não vivem
// mais no navegador: vêm do backend por REST + SSE (state/projetos.ts).
import type { Movimento } from '../types';

export const COR_SORA = '#E2ECFF';
export const PALETA_AGENTES = ['#56A8FF', '#AC80FF', '#46E8A8', '#FF6FAE', '#FFB45E', '#45D4E8', '#F279C6', '#8FD36B', '#6F8CFF', '#E77DFF'] as const;
export const MOVIMENTOS: { id: Movimento; nome: string; descricao: string }[] = [
  { id: 'gira', nome: 'Giro', descricao: 'Rotação suave e contínua' },
  { id: 'vibracao', nome: 'Vibração', descricao: 'Movimento fino e rápido' },
  { id: 'espiral', nome: 'Espiral', descricao: 'Torção dos pontos em hélice' },
  { id: 'ondas', nome: 'Ondas', descricao: 'Ondulação pela superfície' },
];
