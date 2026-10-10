import type { CSSProperties } from 'react';
import type { PassoTrabalho } from '../../types';
import type { AgenteSora, SoraPerfil } from '../../state/projetos';
import { SoraOrb } from '../mascot';
import { ChamadaFerramenta, ResultadoResumo } from './ChamadaFerramenta';

/** Bloco destacado com o prompt que o agente recebeu (da Sora ou do usuário). */
export function BlocoPrompt({ passo, nomeSora = 'Sora', corSora = '#E2ECFF' }: { passo: PassoTrabalho; nomeSora?: string; corSora?: string }) {
  const daSora = passo.origem !== 'usuario';
  return (
    <div className="wk-prompt">
      <div className="wk-prompt-from">
        {daSora ? <SoraOrb size={20} color={corSora} state="idle" glow={false} title={nomeSora} /> : <span className="wk-you">Você</span>}
        <span>{daSora ? `${nomeSora} pediu` : 'Você pediu'}</span>
      </div>
      <p>{passo.texto}</p>
    </div>
  );
}

interface Contexto { sora: SoraPerfil; agentes: Record<string, AgenteSora> }

function Passo({ passo, agente, agora, ctx }: { passo: PassoTrabalho; agente: AgenteSora; agora: number; ctx: Contexto }) {
  const cor = agente.cor;
  if (passo.tipo === 'prompt') return <BlocoPrompt passo={passo} nomeSora={ctx.sora.nome} corSora={ctx.sora.cor} />;
  if (passo.tipo === 'pensamento') {
    return (
      <div className={`wk-thought wk-${passo.status}`}>
        {passo.status === 'executando' ? <span className="shimmer">{passo.texto}</span> : <span>{passo.texto}</span>}
      </div>
    );
  }
  if (passo.tipo === 'ferramenta') return <ChamadaFerramenta passo={passo} cor={cor} movimento={agente.tipoMovimento} agora={agora} />;
  if (passo.tipo === 'entrega') {
    return (
      <div className="wk-delivery">
        <div className="wk-delivery-head"><b>Entrega</b><span>{passo.texto}</span></div>
        {passo.resultado && <ResultadoResumo resultado={passo.resultado} cor={cor} />}
      </div>
    );
  }
  // handoff
  const para = passo.paraAgenteId ? ctx.agentes[passo.paraAgenteId] : undefined;
  return (
    <div className="wk-handoff" style={{ '--to': para?.cor ?? cor } as CSSProperties}>
      <span>↗</span>{passo.texto}
    </div>
  );
}

/** Linha do tempo de passos de um agente. */
export function LinhaDoTempo({ passos, agente, agora, sora, agentes }: { passos: PassoTrabalho[]; agente: AgenteSora; agora: number } & Contexto) {
  return (
    <ol className="wk-timeline" style={{ '--agent': agente.cor } as CSSProperties}>
      {passos.map(p => (
        <li key={p.id} className={`wk-step wk-step-${p.tipo} wk-${p.status}`}>
          <i className="wk-node" aria-hidden="true" />
          <Passo passo={p} agente={agente} agora={agora} ctx={{ sora, agentes }} />
        </li>
      ))}
    </ol>
  );
}
