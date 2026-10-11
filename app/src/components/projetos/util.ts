// Utilitários da tela Projetos: filtro por fase, cores de fase e data relativa em PT-BR.
import type { FaseProjeto } from '../../state/projetos';

export type FiltroProjetos = 'todos' | 'andamento' | 'prontos' | 'aprovados';

export const FILTROS: { id: FiltroProjetos; rotulo: string }[] = [
  { id: 'todos', rotulo: 'Todos' },
  { id: 'andamento', rotulo: 'Em andamento' },
  { id: 'prontos', rotulo: 'Prontos' },
  { id: 'aprovados', rotulo: 'Aprovados' },
];

export function grupoDaFase(fase: FaseProjeto): Exclude<FiltroProjetos, 'todos'> {
  if (fase === 'aprovado') return 'aprovados';
  if (fase === 'pronto' || fase === 'conversa') return 'prontos';
  return 'andamento';
}

/** Rótulo e cor de cada fase (cor = o que a Sora está fazendo; verde = concluído). */
export const FASES: Record<FaseProjeto, { rotulo: string; cor: string }> = {
  pensando: { rotulo: 'Sora pensando', cor: 'var(--sora)' },
  conversa: { rotulo: 'Conversa', cor: 'var(--text-2)' },
  planejando: { rotulo: 'Criando a equipe', cor: '#9cc4ff' },
  coordenando: { rotulo: 'Em andamento', cor: '#9cc4ff' },
  pronto: { rotulo: 'Pronto para revisar', cor: 'var(--ok)' },
  aprovado: { rotulo: 'Aprovado', cor: 'var(--ok)' },
};

const fmtData = new Intl.DateTimeFormat('pt-BR', { day: 'numeric', month: 'short' });
const fmtDataAno = new Intl.DateTimeFormat('pt-BR', { day: 'numeric', month: 'short', year: 'numeric' });

/** "agora mesmo", "há 5 min", "há 2 h", "ontem", "há 3 dias", "12 de out." */
export function tempoRelativo(quando: number, agora = Date.now()): string {
  const s = Math.max(0, Math.round((agora - quando) / 1000));
  if (s < 45) return 'agora mesmo';
  const min = Math.round(s / 60);
  if (min < 60) return `há ${min} min`;
  const h = Math.round(min / 60);
  const hoje = new Date(agora); hoje.setHours(0, 0, 0, 0);
  if (quando >= hoje.getTime()) return `há ${h} h`;
  const dias = Math.ceil((hoje.getTime() - quando) / 86_400_000);
  if (dias <= 1) return 'ontem';
  if (dias < 7) return `há ${dias} dias`;
  return (new Date(quando).getFullYear() === new Date(agora).getFullYear() ? fmtData : fmtDataAno).format(quando);
}

/** Pedido resumido para o card. */
export const resumirPedido = (t: string, max = 120) => t.length > max ? `${t.slice(0, max - 1).trimEnd()}…` : t;

/** Busca sem acento e sem caixa. */
export const normalizar = (t: string) => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

export const ID_COMPOSITOR = 'pj-novo';

/** Leva o foco ao campo do compositor (depois de um modelo preencher o texto). */
export function focarCompositor() {
  const campo = document.querySelector<HTMLTextAreaElement>(`#${ID_COMPOSITOR} textarea`);
  if (!campo) return;
  campo.scrollIntoView({ block: 'center', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  campo.focus({ preventScroll: true });
  campo.setSelectionRange(campo.value.length, campo.value.length);
}
