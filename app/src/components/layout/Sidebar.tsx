// Barra lateral: navegação (Novo chat, Projetos, Agentes, Plugins) + CHATS.
// Ao abrir o app, CHATS está vazio. Cada conversa com a Sora e cada agente criado aparecem aqui.
import { useRef, useState, type CSSProperties, type JSX } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { SoraOrb } from '../mascot';
import { usuario } from '../../data/mock';
import { estadoAgente, estadoProjeto, novoChat, useAgora, useProjetos, type AgenteSora, type ProjetoSora } from '../../state/projetos';
import { pedirApagar, pedirRenomear } from '../gestao';
import { AccountMenu } from '../review/AccountMenu';
import { Tooltip } from '../base';
import { MenuAgente } from '../builder';
import { AgentsIcon, FolderIcon, GearIcon, GridIcon, PlusIcon } from '../ui/Icons';
import { statusCurto } from './useSoraStatus';

function LinhaAgente({ a, onNavegar, filho }: { a: AgenteSora; onNavegar?: () => void; filho?: boolean }) {
  const e = useProjetos();
  const agora = useAgora();
  const navigate = useNavigate();
  const st = estadoAgente(e, a.id, agora);
  const sc = statusCurto(e, a.id, agora);
  const recemNascido = agora - a.criadoEm < 2000;
  return (
    <div className={`chat-row ${recemNascido ? 'is-born' : ''} ${filho ? 'is-child' : ''}`} style={{ '--agent': a.cor } as CSSProperties}>
      <Tooltip conteudo={<><strong>{a.nome}</strong> · {sc.completo}</>} lado="baixo">
        <NavLink to={`/chat/${a.id}`} onClick={onNavegar}>
          <SoraOrb size={28} color={a.cor} movimento={a.tipoMovimento} glow={false} decorative seed={a.nome.length}
            state={st.status === 'trabalhando' ? 'working' : st.status === 'concluido' ? 'done' : recemNascido ? 'arriving' : 'idle'} />
          <span><strong>{a.nome}</strong><small className={st.status === 'trabalhando' ? 'agent-color' : ''}>{sc.curto}</small></span>
          <i className={`status-dot status-${st.status}`} role="img" aria-label={st.status === 'concluido' ? 'Concluído' : st.status === 'trabalhando' ? 'Trabalhando' : 'Aguardando'} />
        </NavLink>
      </Tooltip>
      <MenuAgente agenteId={a.id} nome={a.nome} className="chat-row-menu" itens={[
        { rotulo: 'Ver trabalho', onClick: () => { navigate(`/chat/${a.id}?painel=trabalho`); onNavegar?.(); } },
        { rotulo: 'Renomear', onClick: () => pedirRenomear({ tipo: 'agente', id: a.id }) },
        { rotulo: 'Apagar', perigo: true, onClick: () => pedirApagar({ tipo: 'agente', id: a.id }) },
      ]} />
    </div>
  );
}

function LinhaChat({ p, onNavegar }: { p: ProjetoSora; onNavegar?: () => void }) {
  const e = useProjetos();
  const agora = useAgora();
  const fase = estadoProjeto(e, p, agora).fase;
  const pensando = fase === 'pensando';
  return (
    <div className="chat-row chat-row-sora">
      <NavLink to={`/projeto/${p.id}`} onClick={onNavegar}>
        <SoraOrb size={28} color={e.sora.cor} glow={false} decorative seed={p.titulo.length}
          state={pensando ? 'thinking' : fase === 'coordenando' || fase === 'planejando' ? 'coordinating' : 'idle'} />
        <span><strong>{p.titulo}</strong><small>{pensando ? 'Pensando…' : p.agenteIds.length ? `${p.agenteIds.length} agentes` : e.sora.nome}</small></span>
        {pensando && <i className="status-dot status-thinking" aria-hidden="true" />}
      </NavLink>
      <MenuAgente agenteId={p.id} nome={p.titulo} className="chat-row-menu" semEditar itens={[
        { rotulo: 'Renomear', onClick: () => pedirRenomear({ tipo: 'projeto', id: p.id }) },
        { rotulo: 'Apagar', perigo: true, onClick: () => pedirApagar({ tipo: 'projeto', id: p.id }) },
      ]} />
    </div>
  );
}

/** Conteúdo de navegação (também usado no menu do celular). */
export function Navegacao({ onNavegar }: { onNavegar?: () => void }) {
  const e = useProjetos();
  const agora = useAgora();
  // grupos, mais recentes primeiro: cada chat seguido dos seus agentes; agentes de projetos e avulsos soltos
  const nascidos = (ids: string[]) => ids.map(id => e.agentes[id]).filter((a): a is AgenteSora => !!a && a.criadoEm <= agora);
  const grupos: { t: number; linhas: { k: string; el: JSX.Element }[] }[] = [];
  for (const p of e.projetos) {
    const ags = nascidos(p.agenteIds).map(a => ({ k: `a-${a.id}`, el: <LinhaAgente a={a} onNavegar={onNavegar} filho={p.tipo === 'chat'} /> }));
    if (p.tipo === 'chat') grupos.push({ t: p.criadoEm, linhas: [{ k: `c-${p.id}`, el: <LinhaChat p={p} onNavegar={onNavegar} /> }, ...ags] });
    else if (ags.length) grupos.push({ t: p.criadoEm, linhas: ags });
  }
  const naEquipe = new Set(e.projetos.flatMap(p => p.agenteIds));
  for (const a of Object.values(e.agentes)) {
    if (!naEquipe.has(a.id) && a.criadoEm <= agora) grupos.push({ t: a.criadoEm, linhas: [{ k: `a-${a.id}`, el: <LinhaAgente a={a} onNavegar={onNavegar} /> }] });
  }
  const itens = grupos.sort((x, y) => y.t - x.t).flatMap(g => g.linhas);
  return (
    <>
      <nav className="main-nav" aria-label="Principal">
        <NavLink to="/" end onClick={() => { novoChat(); onNavegar?.(); }}><PlusIcon /><span>Novo chat</span></NavLink>
        <NavLink to="/projetos" onClick={onNavegar}><FolderIcon /><span>Projetos</span></NavLink>
        <NavLink to="/agentes" onClick={onNavegar}><AgentsIcon /><span>Agentes</span></NavLink>
        <NavLink to="/plugins" onClick={onNavegar}><GridIcon /><span>Plugins</span></NavLink>
      </nav>
      {itens.length > 0 && <>
        <p className="eyebrow chats-label" id="chats-titulo">Chats</p>
        <div className="chat-nav" role="list" aria-labelledby="chats-titulo">
          {itens.map(i => <div role="listitem" key={i.k}>{i.el}</div>)}
        </div>
      </>}
    </>
  );
}

export function Sidebar() {
  const { sora } = useProjetos();
  const [conta, setConta] = useState(false);
  const contaRef = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();
  return (
    <aside className="sidebar" aria-label="Navegação principal">
      <NavLink to="/" className="brand" aria-label="Sora, novo chat" onClick={() => novoChat()}>
        <SoraOrb size={22} color={sora.cor} glow={false} decorative seed={3} /><span>Sora</span>
      </NavLink>
      <div className="sidebar-scroll"><Navegacao /></div>
      <div className="account">
        <span className="account-avatar" aria-hidden="true">{usuario.empresa.slice(0, 1)}</span>
        <span><strong>{usuario.empresa}</strong><small>{usuario.plano}</small></span>
        <NavLink to="/configuracoes" className="account-settings" aria-label="Configurações" title="Configurações"><GearIcon /></NavLink>
        <button ref={contaRef} type="button" aria-label="Abrir menu da conta" aria-haspopup="menu" aria-expanded={conta} onClick={() => setConta(v => !v)}>•••</button>
        <AccountMenu open={conta} onClose={() => setConta(false)} anchorRef={contaRef} empresa={usuario.empresa} plano={usuario.plano}
          onSelect={a => { if (a === 'plugins') navigate('/plugins'); if (a === 'configuracoes') navigate('/configuracoes'); if (a === 'sair') { novoChat(); navigate('/'); } }} />
      </div>
    </aside>
  );
}
