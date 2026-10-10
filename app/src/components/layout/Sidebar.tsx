// Barra lateral: ao abrir só existe a Sora. Agentes "nascem" aqui conforme a Sora cria a equipe.
import { useRef, useState, type CSSProperties } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { SoraOrb } from '../mascot';
import { usuario } from '../../data/mock';
import {
  abrirProjeto, agentesAvulsos, agentesDoProjeto, estadoAgente, estadoProjeto, novoChat, projetoAtivo,
  useAgora, useProjetos, type AgenteSora,
} from '../../state/projetos';
import { AccountMenu } from '../review/AccountMenu';
import { MenuAgente } from '../studio';
import { GridIcon, PlusIcon } from '../ui/Icons';
import { rotuloFase, statusDaSora } from './useSoraStatus';

function LinhaAgente({ a, onNavegar }: { a: AgenteSora; onNavegar?: () => void }) {
  const e = useProjetos();
  const agora = useAgora();
  const navigate = useNavigate();
  const st = estadoAgente(e, a.id, agora);
  return (
    <div className={`chat-row ${agora - a.criadoEm < 2000 ? 'is-born' : ''}`} style={{ '--agent': a.cor } as CSSProperties}>
      <NavLink to={`/chat/${a.id}`} onClick={onNavegar}>
        <SoraOrb size={34} color={a.cor} movimento={a.tipoMovimento} glow={false} decorative seed={a.nome.length}
          state={st.status === 'trabalhando' ? 'working' : st.status === 'concluido' ? 'done' : agora - a.criadoEm < 2000 ? 'arriving' : 'idle'} />
        <span><strong>{a.nome}</strong><small className={st.status === 'trabalhando' ? 'agent-color' : ''}>{st.rotulo || a.funcao}</small></span>
        <i className={`status-dot status-${st.status}`} role="img" aria-label={st.status === 'concluido' ? 'Concluído' : st.status === 'trabalhando' ? 'Trabalhando' : 'Aguardando'} />
      </NavLink>
      <MenuAgente agenteId={a.id} nome={a.nome} className="chat-row-menu" itens={[
        { rotulo: 'Ver trabalho', onClick: () => { navigate(`/chat/${a.id}?painel=trabalho`); onNavegar?.(); } },
        { rotulo: 'Conversar', onClick: () => { navigate(`/chat/${a.id}`); onNavegar?.(); } },
      ]} />
    </div>
  );
}

/** Conteúdo de navegação (também usado no menu do celular). */
export function Navegacao({ onNavegar }: { onNavegar?: () => void }) {
  const e = useProjetos();
  const agora = useAgora();
  const navigate = useNavigate();
  const p = projetoAtivo(e);
  const sora = statusDaSora(e, agora);
  const equipe = agentesDoProjeto(e, p, agora);
  const avulsos = agentesAvulsos(e);
  return (
    <>
      <nav className="main-nav" aria-label="Principal">
        <NavLink to="/" end onClick={() => { novoChat(); onNavegar?.(); }}><PlusIcon /><span>Novo chat</span></NavLink>
        <NavLink to="/plugins" onClick={onNavegar}><GridIcon /><span>Plugins</span></NavLink>
      </nav>

      <p className="eyebrow chats-label" id="chats-titulo">Chats</p>
      <div className="chat-nav" role="list" aria-labelledby="chats-titulo">
        <div className="chat-row" role="listitem">
          <NavLink to="/chat/sora" onClick={onNavegar}>
            <SoraOrb size={34} color={e.sora.cor} state={sora.orb} pulseKey={sora.pulso} glow={false} decorative seed={11} />
            <span><strong>{e.sora.nome}</strong><small role="status">{sora.rotulo}</small></span>
            <i className={`status-dot ${sora.orb === 'thinking' ? 'status-thinking' : 'status-online'}`} aria-hidden="true" />
          </NavLink>
          <MenuAgente agenteId="sora" nome={e.sora.nome} className="chat-row-menu" />
        </div>
        {equipe.map(a => <div role="listitem" key={a.id}><LinhaAgente a={a} onNavegar={onNavegar} /></div>)}
        {avulsos.map(a => <div role="listitem" key={a.id}><LinhaAgente a={a} onNavegar={onNavegar} /></div>)}
      </div>

      {e.projetos.length > 0 && <>
        <p className="eyebrow chats-label" id="projetos-titulo">Projetos</p>
        <div className="project-nav" role="list" aria-labelledby="projetos-titulo">
          {e.projetos.map(proj => {
            const fase = estadoProjeto(e, proj, agora).fase;
            return (
              <button type="button" role="listitem" key={proj.id} className={`project-row ${proj.id === p?.id ? 'is-on' : ''}`}
                aria-current={proj.id === p?.id ? 'true' : undefined}
                onClick={() => { abrirProjeto(proj.id); navigate('/chat/sora'); onNavegar?.(); }}>
                <strong>{proj.titulo}</strong>
                <small className={`fase-${fase}`}>{rotuloFase[fase]}</small>
              </button>
            );
          })}
        </div>
      </>}
    </>
  );
}

export function Sidebar() {
  const [conta, setConta] = useState(false);
  const contaRef = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();
  return (
    <aside className="sidebar" aria-label="Navegação principal">
      <NavLink to="/" className="brand" aria-label="Sora, novo chat" onClick={() => novoChat()}>Sora</NavLink>
      <div className="sidebar-scroll"><Navegacao /></div>
      <div className="account">
        <span className="account-avatar" aria-hidden="true">{usuario.empresa.slice(0, 1)}</span>
        <span><strong>{usuario.empresa}</strong><small>{usuario.plano}</small></span>
        <button ref={contaRef} type="button" aria-label="Abrir menu da conta" aria-haspopup="menu" aria-expanded={conta} onClick={() => setConta(v => !v)}>•••</button>
        <AccountMenu open={conta} onClose={() => setConta(false)} anchorRef={contaRef} empresa={usuario.empresa} plano={usuario.plano}
          onSelect={a => { if (a === 'plugins') navigate('/plugins'); if (a === 'configuracoes') navigate('/agentes'); if (a === 'sair') { novoChat(); navigate('/'); } }} />
      </div>
    </aside>
  );
}
