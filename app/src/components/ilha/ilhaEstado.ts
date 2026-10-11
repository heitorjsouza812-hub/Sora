// Ilha da Sora — CONTRATO de dados (adaptação do Coucou: https://github.com/Louis-CFM/coucou).
// A ilha mostra, no topo da tela, a Sora (branca, principal) e os agentes que estão rodando
// no projeto escolhido. Tudo é derivado do store de projetos + relógio (nada novo é simulado aqui).
// As peças visuais (Ilha, VisaoGeral, SeletorProjeto, DetalheAgente…) usam SÓ o que este arquivo exporta.
import { useSyncExternalStore } from 'react';
import type { Movimento, PassoTrabalho, Status } from '../../types';
import type { OrbState } from '../mascot';
import {
  agentesDoProjeto, estadoAgente, estadoProjeto, passosDoAgente, useAgora, useProjetos,
  type EstadoProjetos, type FaseProjeto, type ProjetoSora,
} from '../../state/projetos';
import { statusDaSora } from '../layout/useSoraStatus';

// ---------- preferências (localStorage 'sora.ilha.v1') ----------

export interface IlhaPrefs {
  /** mostrar a ilha no app */
  visivel: boolean;
  /** sons curtos (agente concluiu, equipe pronta, abrir) */
  som: boolean;
  /** como no Coucou: sem nada rodando, a ilha se recolhe e só "espia" ao passar o mouse no topo */
  esconderOciosa: boolean;
  /** projeto escolhido na aba de projetos; null = automático (o projeto aberto ou o que está rodando) */
  projetoId: string | null;
}

const CHAVE = 'sora.ilha.v1';
const PADRAO: IlhaPrefs = { visivel: true, som: true, esconderOciosa: false, projetoId: null };

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

// ---------- visão derivada ----------

export interface ResumoProjetoIlha {
  id: string;
  titulo: string;
  fase: FaseProjeto;
  /** pensando · planejando · coordenando · pronto (esperando revisão) */
  rodando: boolean;
  trabalhando: number;          // agentes com status 'trabalhando' agora
  total: number;                // agentes da equipe já nascidos
  progresso: number;            // 0..100
  cores: string[];              // cores dos agentes (para as mini-bolinhas da aba)
}

export interface AgenteIlha {
  id: string;
  nome: string;
  funcao: string;
  cor: string;
  movimento: Movimento;
  status: Status;
  rotulo: string;               // "Pesquisando", "Aguardando referências", "Concluído"…
  progresso: number;            // 0..100
  orb: OrbState;                // estado pronto para o <SoraOrb>
  passoAtual: PassoTrabalho | null; // o que está fazendo agora (último passo iniciado)
}

export interface AlertaIlha {
  tipo: 'revisar';              // equipe terminou: o usuário aprova ou pede ajuste (nada é publicado sem aprovação)
  projetoId: string;
  titulo: string;
  entregas: string[];           // ex.: ["Pesquisa · 4 referências", "Peças · 3 peças"]
}

export interface VisaoIlha {
  projetos: ResumoProjetoIlha[];      // todos (rodando primeiro, depois os mais recentes)
  projeto: ResumoProjetoIlha | null;  // o projeto mostrado
  automatico: boolean;                // true quando a escolha veio do modo automático
  agentes: AgenteIlha[];              // os "bonecos": agentes do projeto mostrado
  sora: { nome: string; cor: string; orb: OrbState; rotulo: string; pulso: number };
  ticker: PassoTrabalho[];            // últimos passos (mais recente por último), no máx. 6
  trabalhando: number;                // agentes trabalhando em TODOS os projetos
  rodando: number;                    // projetos rodando
  alerta: AlertaIlha | null;
}

const RODANDO: FaseProjeto[] = ['pensando', 'planejando', 'coordenando', 'pronto'];

function resumir(e: EstadoProjetos, p: ProjetoSora, agora: number): ResumoProjetoIlha {
  const ep = estadoProjeto(e, p, agora);
  const ags = agentesDoProjeto(e, p, agora);
  return {
    id: p.id, titulo: p.titulo, fase: ep.fase, rodando: RODANDO.includes(ep.fase),
    trabalhando: ags.filter(a => estadoAgente(e, a.id, agora).status === 'trabalhando').length,
    total: ags.length, progresso: ep.progresso, cores: ags.map(a => a.cor),
  };
}

const orbDoStatus = (s: Status): OrbState => s === 'trabalhando' ? 'working' : s === 'concluido' ? 'done' : 'idle';

/** Função pura (testável): monta a visão da ilha. */
export function visaoIlha(e: EstadoProjetos, agora: number, escolhido: string | null): VisaoIlha {
  const resumos = e.projetos.map(p => resumir(e, p, agora));
  const projetos = [...resumos.filter(r => r.rodando), ...resumos.filter(r => !r.rodando)];

  // escolha: manual (se ainda existe) → projeto aberto → primeiro rodando → mais recente
  const manual = escolhido ? resumos.find(r => r.id === escolhido) ?? null : null;
  const auto = resumos.find(r => r.id === e.projetoAtivoId) ?? projetos.find(r => r.rodando) ?? resumos[0] ?? null;
  const projeto = manual ?? auto;
  const p = projeto ? e.projetos.find(x => x.id === projeto.id) ?? null : null;

  const agentes: AgenteIlha[] = agentesDoProjeto(e, p, agora).map(a => {
    const st = estadoAgente(e, a.id, agora);
    const passos = passosDoAgente(e, a.id, agora);
    return {
      id: a.id, nome: a.nome, funcao: a.funcao, cor: a.cor, movimento: a.tipoMovimento,
      status: st.status, rotulo: st.rotulo || a.funcao, progresso: st.progresso, orb: orbDoStatus(st.status),
      passoAtual: st.status === 'trabalhando' ? passos[passos.length - 1] ?? null : null,
    };
  });

  const ticker = p
    ? agentes.flatMap(a => passosDoAgente(e, a.id, agora)).sort((a, b) => a.inicio - b.inicio).slice(-6)
    : [];

  // a Sora reflete o projeto mostrado (statusDaSora lê o projeto ativo; aqui trocamos pelo escolhido)
  const s = statusDaSora(p ? { ...e, projetoAtivoId: p.id } : { ...e, projetoAtivoId: null }, agora);

  const pronto = p && projeto?.fase === 'pronto' ? p : e.projetos.find(x => estadoProjeto(e, x, agora).fase === 'pronto') ?? null;
  const alerta: AlertaIlha | null = pronto ? {
    tipo: 'revisar', projetoId: pronto.id, titulo: pronto.titulo,
    entregas: Object.values(pronto.entregas).map(en => `${en.titulo} · ${en.resumo}`),
  } : null;

  return {
    projetos, projeto, automatico: !manual, agentes,
    sora: { nome: e.sora.nome, cor: e.sora.cor, orb: s.orb, rotulo: s.rotulo, pulso: s.pulso },
    ticker,
    trabalhando: Object.keys(e.agentes).filter(id => estadoAgente(e, id, agora).status === 'trabalhando').length,
    rodando: projetos.filter(r => r.rodando).length,
    alerta,
  };
}

/** Hook usado pelos componentes da ilha. */
export function useIlha(): VisaoIlha {
  const e = useProjetos();
  const agora = useAgora();
  const { projetoId } = useIlhaPrefs();
  return visaoIlha(e, agora, projetoId);
}
