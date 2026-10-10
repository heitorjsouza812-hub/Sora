import type { OrbState } from '../mascot';
import { agentesDoProjeto, estadoAgente, estadoProjeto, projetoAtivo, type EstadoProjetos } from '../../state/projetos';

/** Estado da Sora (orb + rótulo + pulso) a partir do projeto ativo. */
export function statusDaSora(e: EstadoProjetos, agora: number): { orb: OrbState; rotulo: string; pulso: number; fase: string | null } {
  const p = projetoAtivo(e);
  if (!p) return { orb: 'idle', rotulo: 'Agente principal', pulso: 0, fase: null };
  const ep = estadoProjeto(e, p, agora);
  const n = agentesDoProjeto(e, p, agora).length;
  switch (ep.fase) {
    case 'pensando': return { orb: 'thinking', rotulo: 'Pensando…', pulso: ep.pulso, fase: ep.fase };
    case 'planejando': return { orb: 'coordinating', rotulo: n ? `Criando a equipe · ${n} de ${p.agenteIds.length}` : 'Montando o plano…', pulso: ep.pulso, fase: ep.fase };
    case 'coordenando': return { orb: 'coordinating', rotulo: `Coordenando ${n} ${n === 1 ? 'agente' : 'agentes'}`, pulso: ep.pulso, fase: ep.fase };
    case 'conversa': return { orb: 'idle', rotulo: 'Online', pulso: ep.pulso, fase: ep.fase };
    case 'pronto': return { orb: 'done', rotulo: 'Pronto para revisar', pulso: ep.pulso, fase: ep.fase };
    default: return { orb: 'done', rotulo: 'Projeto aprovado', pulso: ep.pulso, fase: ep.fase };
  }
}

export const rotuloFase: Record<string, string> = {
  pensando: 'Pensando', conversa: 'Conversa', planejando: 'Planejando', coordenando: 'Em andamento', pronto: 'Pronto para revisar', aprovado: 'Aprovado',
};

/**
 * Status CURTO de um agente para a barra lateral (cabe sem cortar) + o texto completo para o Tooltip.
 * 'Pesquisando' · 'Pronto' · 'Esperando Atlas' · 'Na fila' · 'Disponível'.
 */
export function statusCurto(e: EstadoProjetos, agenteId: string, agora: number): { curto: string; completo: string } {
  const a = e.agentes[agenteId];
  if (!a) return { curto: '', completo: '' };
  const st = estadoAgente(e, agenteId, agora);
  const completo = `${a.funcao} · ${st.rotulo || 'Disponível'}`;
  if (st.status === 'trabalhando') return { curto: a.verbo, completo };
  if (st.status === 'concluido') return { curto: 'Pronto', completo };
  if (a.avulso) return { curto: 'Disponível', completo };
  // na equipe: quem vem antes na fila e ainda não terminou?
  const p = e.projetos.find(x => x.agenteIds.includes(agenteId));
  const i = p ? p.tarefas.findIndex(t => t.agenteId === agenteId) : -1;
  const anterior = p && i > 0 ? e.agentes[p.tarefas[i - 1].agenteId] : undefined;
  if (anterior && estadoAgente(e, anterior.id, agora).status !== 'concluido') return { curto: `Esperando ${anterior.nome}`, completo };
  return { curto: 'Na fila', completo };
}
