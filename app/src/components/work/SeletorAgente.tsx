import type { CSSProperties } from 'react';
import type { AgenteSora, EstadoAgente } from '../../state/projetos';
import { SoraOrb } from '../mascot';

/** Chips para escolher qual agente acompanhar no painel Trabalho. */
export function SeletorAgente({ agentes, estados, atual, onEscolher }: {
  agentes: AgenteSora[]; estados: Record<string, EstadoAgente>; atual?: string; onEscolher: (id: string) => void;
}) {
  return (
    <div className="wk-picker" role="tablist" aria-label="Acompanhar agente">
      {agentes.map(a => {
        const st = estados[a.id]?.status ?? 'aguardando';
        return (
          <button key={a.id} type="button" role="tab" aria-selected={a.id === atual}
            className={`wk-chip ${a.id === atual ? 'is-on' : ''}`} style={{ '--agent': a.cor } as CSSProperties} onClick={() => onEscolher(a.id)}>
            <SoraOrb size={22} color={a.cor} movimento={a.tipoMovimento} glow={false} title={a.nome}
              state={st === 'trabalhando' ? 'working' : st === 'concluido' ? 'done' : 'idle'} />
            <span>{a.nome}</span>
            <i className={`wk-dot wk-dot-${st}`} aria-label={st} />
          </button>
        );
      })}
    </div>
  );
}
