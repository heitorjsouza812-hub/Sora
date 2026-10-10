import type { Movimento } from '../../types';
import type { RascunhoAgente } from '../../state/projetos';
import type { EscolhaModelo } from '../../state/modelos';

export interface RascunhoConstrutor extends RascunhoAgente {
  id?: string;
  descricaoCurta: string;
  frasesIniciais: string[];
  tom: 'objetivo' | 'amigavel' | 'criativo' | 'tecnico';
  modelo: EscolhaModelo | null;
}
export interface MensagemConstrutor { id: string; autor: 'sora' | 'usuario'; texto: string }
export type AbaConstrutor = 'criar' | 'configurar' | 'previa';
export const MOVIMENTOS_CONSTRUTOR: { id: Movimento; nome: string }[] = [
  { id: 'gira', nome: 'Gira' }, { id: 'vibracao', nome: 'Vibração' }, { id: 'espiral', nome: 'Espiral' }, { id: 'ondas', nome: 'Ondas' },
];

