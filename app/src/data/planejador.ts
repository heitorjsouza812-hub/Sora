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

export function verboPara(funcao: string) {
  const f = funcao.toLowerCase();
  if (/pesquis|refer|mercado/.test(f)) return 'Pesquisando';
  if (/texto|copy|redat|escrev/.test(f)) return 'Escrevendo';
  if (/design|visual|imagem|arte/.test(f)) return 'Criando';
  if (/c[oó]digo|program|site/.test(f)) return 'Programando';
  if (/an[aá]lis|dado|m[eé]tric/.test(f)) return 'Analisando';
  return 'Trabalhando';
}

export interface RascunhoAgenteLocal {
  nome: string; funcao: string; cor: string; tipoMovimento: Movimento; ferramentas: string[]; instrucoes: string;
}

/** Sugestão local apenas para preencher o formulário do construtor. O perfil definitivo é
 * validado e persistido por POST /v1/agentes; isto não cria trabalho, plano nem resposta falsa. */
export function agenteDeDescricao(descricao: string): RascunhoAgenteLocal {
  const d = descricao.toLowerCase();
  const regra = /pesquis|refer|mercado/.test(d)
    ? { funcao: 'Pesquisa e referências', movimento: 'vibracao' as const }
    : /imag|visual|design|arte/.test(d)
      ? { funcao: 'Criação visual', movimento: 'espiral' as const }
      : /texto|copy|escrev|legenda/.test(d)
        ? { funcao: 'Textos', movimento: 'ondas' as const }
        : { funcao: 'Assistente', movimento: 'gira' as const };
  return {
    nome: 'Novo agente', funcao: regra.funcao, cor: PALETA_AGENTES[0], tipoMovimento: regra.movimento, ferramentas: [],
    instrucoes: descricao.trim(),
  };
}
