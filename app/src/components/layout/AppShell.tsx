import type { CSSProperties, ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { agentes } from '../../data/mock';
import { useSora } from '../../state/SoraContext';
import { SoraOrb } from '../mascot';
import { Sidebar } from './Sidebar';

export function AppShell({ title, children }: { title: string; children: ReactNode }) {
  const { state, statusAgente } = useSora();
  const agente = agentes.find((item) => item.nome === title);
  const indice = agente ? agentes.indexOf(agente) : -1;
  const status = indice >= 0 ? statusAgente(indice) : null;
  const soraThinking = ['enviado', 'pensando'].includes(state.fase);
  const nome = agente?.nome ?? 'Sora';
  const subtitulo = agente
    ? status === 'concluido' ? 'Concluído' : status === 'trabalhando' ? agente.verbo : agente.espera
    : soraThinking ? 'Pensando…'
      : state.fase === 'coordenando' ? 'Coordenando 3 agentes'
        : state.fase === 'pronto' ? 'Campanha pronta' : title === 'Novo chat' ? 'Disponível' : title === 'Sora' ? 'Agente principal' : title;
  const orbState = agente
    ? status === 'trabalhando' ? 'working' : status === 'concluido' ? 'done' : 'idle'
    : soraThinking ? 'thinking' : state.fase === 'pronto' ? 'done' : state.fase === 'coordenando' ? 'coordinating' : 'idle';
  const cor = agente?.cor ?? '#7EF2C4';

  return (
    <div className="app-shell">
      <Sidebar />
      <section className="app-stage">
        <header className="topbar" style={{ '--header-accent': cor } as CSSProperties}>
          <div className="topbar-identity">
            <SoraOrb size={38} color={agente?.cor} movimento={agente?.tipoMovimento} state={orbState} glow={false} seed={91 + Math.max(indice, 0)} title={nome} />
            <span><strong>{nome}</strong><small><i />{subtitulo}</small></span>
          </div>
          <details className="mobile-team-menu">
            <summary>Equipe</summary>
            <nav>
              <NavLink to="/chat/sora">Sora <small>Coordenação</small></NavLink>
              {agentes.map((item, itemIndex) => <NavLink key={item.id} to={`/chat/${item.id}`} style={{ '--agent': item.cor } as CSSProperties}>{item.nome}<small>{statusAgente(itemIndex) === 'concluido' ? 'Concluído' : item.espera}</small></NavLink>)}
            </nav>
          </details>
          <button className="share-button">Compartilhar</button>
        </header>
        {children}
      </section>
    </div>
  );
}

