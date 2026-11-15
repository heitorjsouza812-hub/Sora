// Ilha da Sora — CONTRATO de dados (etapa 5: bots e grupos).
// A ilha só existe na janela dedicada do app de desktop (ver Ilha.tsx: fora dela, nunca renderiza).
// Mostra a Sora (sempre branca, `#E2ECFF` — nunca mudar) e os bots que estão trabalhando, mais o que
// a equipe espera do usuário. Tudo vem de hooks reais: `useBots` (Leme), `useGrupos`/`usePrecisaDeVoce`
// (Mosaico). Nada aqui é simulado — não há mais projetos/agentes de cadeia, que saíram do app nesta etapa.
import { useSyncExternalStore } from 'react';
import { useBots, type BotResumo, type EstadoBot } from '../../state/bots';
import { useGrupos } from '../../state/grupos';
import { usePrecisaDeVoce } from '../../state/atencao';
import type { PedidoAtencao } from '../pendencias/tipos';
import type { OrbState } from '../mascot';

// ---------- preferências (localStorage 'sora.ilha.v1') ----------

export interface IlhaPrefs {
  /** mostrar a ilha fora do app; a janela nativa some de qualquer forma quando a main está em foco */
  visivel: boolean;
  /** sons curtos (abrir, bot concluiu, pedido novo) */
  som: boolean;
  /** como no Coucou: sem nada rodando, a ilha se recolhe e só "espia" ao passar o mouse no topo */
  esconderOciosa: boolean;
  /** quais bonecos mostrar: todos, só os que estão trabalhando, ou só os que precisam de você */
  filtro: FiltroBots;
  /** ids de bots que o usuário escondeu da ilha (botão "olho" em cada boneco) */
  ocultos: string[];
  /** @deprecated etapa 5: a ilha nunca renderiza dentro do app (Tauri mostra/oculta a janela pelo
   *  foco da "main"); campo mantido só para não quebrar preferências salvas antes desta etapa. */
  ilhaNoApp: boolean;
}

export type FiltroBots = 'todos' | 'trabalhando' | 'precisa_de_voce';

const CHAVE = 'sora.ilha.v1';
const PADRAO: IlhaPrefs = {
  visivel: true, som: true, esconderOciosa: false, filtro: 'todos', ocultos: [], ilhaNoApp: false,
};

function carregar(): IlhaPrefs {
  try {
    const bruto = localStorage.getItem(CHAVE);
    if (bruto) return { ...PADRAO, ...(JSON.parse(bruto) as Partial<IlhaPrefs>) };
  } catch { /* armazenamento indisponível: segue com o padrão */ }
  return PADRAO;
}

let prefs: IlhaPrefs = carregar();
const ouvintes = new Set<() => void>();

export function lerIlhaPrefs() { return prefs; }
export function definirIlhaPrefs(patch: Partial<IlhaPrefs>) {
  prefs = { ...prefs, ...patch };
  try { localStorage.setItem(CHAVE, JSON.stringify(prefs)); } catch { /* ignora */ }
  ouvintes.forEach(f => f());
}
function assinar(f: () => void) { ouvintes.add(f); return () => { ouvintes.delete(f); }; }
export function useIlhaPrefs() { return useSyncExternalStore(assinar, lerIlhaPrefs, lerIlhaPrefs); }

// sincroniza entre abas e entre as janelas do app de desktop (app principal + janela da ilha)
if (typeof window !== 'undefined') {
  window.addEventListener('storage', ev => { if (ev.key === CHAVE) { prefs = carregar(); ouvintes.forEach(f => f()); } });
}

/** Esconde/mostra um boneco na ilha. */
export function alternarAgenteOculto(id: string) {
  const ocultos = prefs.ocultos.includes(id) ? prefs.ocultos.filter(x => x !== id) : [...prefs.ocultos, id];
  definirIlhaPrefs({ ocultos });
}

/** Aplica o filtro e os ocultos das preferências (função pura). A ordem é preservada. */
export function filtrarBonecos(bonecos: BonecoIlha[], p: Pick<IlhaPrefs, 'filtro' | 'ocultos'>): BonecoIlha[] {
  return bonecos.filter(a => !p.ocultos.includes(a.id) && (p.filtro === 'todos' || a.estado === p.filtro));
}

// ---------- visão derivada ----------

/** Um "boneco" da ilha: o corpo de pontos de um bot, pequeno e na cor dele. */
export interface BonecoIlha {
  id: string;
  nome: string;
  funcao: string;
  cor: string;
  estado: EstadoBot;
  orb: OrbState;
}

export interface VisaoIlha {
  sora: { nome: string; cor: string };
  bonecos: BonecoIlha[];          // todos os bots da conta (sem filtro de preferência)
  trabalhando: number;            // bots com estado 'trabalhando'
  gruposTrabalhando: number;      // grupos com alguma tarefa em andamento
  precisaDeVoce: PedidoAtencao[]; // cartões "Precisa de você" (Mosaico) de todos os bots/grupos
}

/** A Sora é sempre branca e sempre "Sora" (§3.1 do AGENTS.md) — identidade fixa, não vem de dados. */
const SORA_IDENTIDADE = { nome: 'Sora', cor: '#E2ECFF' } as const;

const orbDoEstado = (estado: EstadoBot): OrbState =>
  estado === 'trabalhando' ? 'working' : estado === 'precisa_de_voce' ? 'listening' : 'idle';

function bonecoDoBot(bot: BotResumo): BonecoIlha {
  return { id: bot.id, nome: bot.nome, funcao: bot.funcao, cor: bot.cor, estado: bot.estado, orb: orbDoEstado(bot.estado) };
}

/** Função pura (testável): monta a visão da ilha a partir dos três hooks reais. */
export function visaoIlha(bots: BotResumo[], gruposTrabalhando: number, precisaDeVoce: PedidoAtencao[]): VisaoIlha {
  const bonecos = bots.map(bonecoDoBot);
  return {
    sora: SORA_IDENTIDADE,
    bonecos,
    trabalhando: bonecos.filter(b => b.estado === 'trabalhando').length,
    gruposTrabalhando,
    precisaDeVoce,
  };
}

/** Hook usado pelos componentes da ilha: combina os bots (Leme), os grupos e os pedidos de atenção
 *  (Mosaico) num único retrato do que está acontecendo agora. */
export function useIlha(): VisaoIlha {
  const bots = useBots();
  const grupos = useGrupos();
  const atencao = usePrecisaDeVoce();
  return visaoIlha(bots, grupos.lista.filter(g => g.trabalhando).length, atencao.lista);
}
