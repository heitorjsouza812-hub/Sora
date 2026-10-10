import { NavLink } from 'react-router-dom';
import { SoraOrb } from '../mascot';
import { agentes, usuario } from '../../data/mock';
import { useSora } from '../../state/SoraContext';
import { GridIcon, PlusIcon } from '../ui/Icons';

const statusLabel = (indice: number, status: string, verbo: string, espera: string) => {
  if (status === 'concluido') return 'Concluído';
  if (status === 'trabalhando') return verbo;
  return indice === 0 ? 'Aguardando' : espera;
};

export function Sidebar() {
  const { state, statusAgente } = useSora();
  return (
    <aside className="sidebar" aria-label="Navegação principal">
      <NavLink to="/" className="brand" aria-label="Sora, novo chat">Sora</NavLink>
      <nav className="main-nav">
        <NavLink to="/" end><PlusIcon /><span>Novo chat</span></NavLink>
        <NavLink to="/plugins"><GridIcon /><span>Plugins</span></NavLink>
      </nav>

      <p className="eyebrow chats-label">Chats</p>
      <nav className="chat-nav" aria-label="Conversas">
        <NavLink to="/chat/sora">
          <SoraOrb size={34} state={state.fase === 'pronto' ? 'done' : state.fase === 'ocioso' ? 'idle' : 'coordinating'} pulseKey={state.pulseKey} glow={false} title="Sora" />
          <span><strong>Sora</strong><small>{state.fase === 'pronto' ? 'Campanha pronta' : state.agentesVisiveis ? 'Coordenando a equipe' : 'Agente principal'}</small></span>
          <i className="status-dot status-online" />
        </NavLink>
        {agentes.map((agente, indice) => {
          const status = statusAgente(indice);
          return (
            <NavLink to={`/chat/${agente.id}`} key={agente.id} style={{ '--agent': agente.cor } as React.CSSProperties}>
              <SoraOrb size={34} color={agente.cor} state={status === 'trabalhando' ? 'working' : status === 'concluido' ? 'done' : 'idle'} movimento={agente.tipoMovimento} pulseKey={state.pulseKey} glow={false} title={agente.nome} />
              <span><strong>{agente.nome}</strong><small className={status === 'trabalhando' ? 'agent-color' : ''}>{statusLabel(indice, status, agente.verbo, agente.espera)}</small></span>
              <i className={`status-dot status-${status}`} />
            </NavLink>
          );
        })}
      </nav>

      <div className="account">
        <span className="account-avatar">C</span>
        <span><strong>{usuario.empresa}</strong><small>{usuario.plano}</small></span>
        <button aria-label="Abrir menu da conta">•••</button>
      </div>
    </aside>
  );
}

