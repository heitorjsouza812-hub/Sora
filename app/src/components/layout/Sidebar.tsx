// Barra lateral: navegação (Novo chat, Projetos, Agentes, Plugins) + CHATS.
// Ao abrir o app, CHATS está vazio. Projeto com equipe → pasta (abre/fecha) com os agentes dentro;
// conversa sem agentes → linha da Sora; agente independente → linha solta.
import { useRef, useState, type CSSProperties, type JSX } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { SoraOrb } from '../mascot';
import { sair, useSessao } from '../../state/sessao';
import { estadoAgente, estadoProjeto, novoChat, useAgora, useProjetos, type AgenteSora, type ProjetoSora } from '../../state/projetos';
import { pedirApagar, pedirRenomear } from '../gestao';
import { AccountMenu } from '../review/AccountMenu';
import { Tooltip } from '../base';
import { IndicadorCreditos } from '../creditos';
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

// pastas de projeto abertas (as pastas começam fechadas; o que o usuário abrir fica lembrado)
const CHAVE_PASTAS = 'sora.pastas.v1';
function lerPastasAbertas(): string[] {
  try { const v = JSON.parse(localStorage.getItem(CHAVE_PASTAS) ?? '[]'); return Array.isArray(v) ? v : []; } catch { return []; }
}
function gravarPastaAberta(id: string, aberta: boolean) {
  const ids = lerPastasAbertas().filter(x => x !== id);
  try { localStorage.setItem(CHAVE_PASTAS, JSON.stringify(aberta ? [...ids, id] : ids)); } catch { /* sem armazenamento: só nesta sessão */ }
}

/** Projeto com equipe: uma pasta que abre/fecha, com os agentes dentro. */
function PastaProjeto({ p, agentes, onNavegar }: { p: ProjetoSora; agentes: AgenteSora[]; onNavegar?: () => void }) {
  const e = useProjetos();
  const agora = useAgora();
  const [aberta, setAberta] = useState(() => lerPastasAbertas().includes(p.id));
  const fase = estadoProjeto(e, p, agora).fase;
  const trabalhando = agentes.filter(a => estadoAgente(e, a.id, agora).status === 'trabalhando');
  const resumo = fase === 'pensando' ? 'Pensando…'
    : trabalhando.length ? `${agentes.length} agentes · ${trabalhando.length} trabalhando`
    : fase === 'pronto' ? 'Pronto para revisar' : fase === 'aprovado' ? 'Aprovado' : `${agentes.length} agentes`;
  const idFilhos = `pasta-${p.id}`;
  const alternar = () => setAberta(v => { gravarPastaAberta(p.id, !v); return !v; });
  return (
    <div className={`chat-pasta ${aberta ? 'is-open' : ''} ${trabalhando.length ? 'is-working' : ''}`}>
      <div className="chat-row chat-row-pasta">
        <button type="button" className="pasta-toggle" aria-expanded={aberta} aria-controls={idFilhos}
          aria-label={`${aberta ? 'Fechar' : 'Abrir'} a pasta ${p.titulo}`} onClick={alternar}>
          {aberta
            ? <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 18V7.5a2 2 0 0 1 2-2h4l2 2.2h6a2 2 0 0 1 2 2V11" /><path d="M3.5 18.5 6.4 12a1.6 1.6 0 0 1 1.5-1h12.4a1 1 0 0 1 .9 1.4l-2.6 5.7a1.6 1.6 0 0 1-1.5.9H4.2" /></svg>
            : <FolderIcon />}
          <i className="pasta-seta" aria-hidden="true" />
        </button>
        <NavLink to={`/projeto/${p.id}`} onClick={onNavegar}>
          <span><strong>{p.titulo}</strong><small>{resumo}</small></span>
          <span className="pasta-cores" aria-hidden="true">
            {agentes.slice(0, 4).map(a => <i key={a.id} style={{ '--agent': a.cor } as CSSProperties}
              className={estadoAgente(e, a.id, agora).status === 'trabalhando' ? 'is-working' : ''} />)}
          </span>
        </NavLink>
        <MenuAgente agenteId={p.id} nome={p.titulo} className="chat-row-menu" semEditar itens={[
          { rotulo: aberta ? 'Fechar pasta' : 'Abrir pasta', onClick: alternar },
          { rotulo: 'Renomear', onClick: () => pedirRenomear({ tipo: 'projeto', id: p.id }) },
          { rotulo: 'Apagar', perigo: true, onClick: () => pedirApagar({ tipo: 'projeto', id: p.id }) },
        ]} />
      </div>
      <div id={idFilhos} className="pasta-filhos" role="group" aria-label={`Agentes de ${p.titulo}`} inert={!aberta}>
        <div>{agentes.map(a => <LinhaAgente key={a.id} a={a} onNavegar={onNavegar} filho />)}</div>
      </div>
    </div>
  );
}

/** Conteúdo de navegação (também usado no menu do celular). */
export function Navegacao({ onNavegar }: { onNavegar?: () => void }) {
  const e = useProjetos();
  const agora = useAgora();
  // mais recentes primeiro: projeto com equipe → pasta com os agentes dentro; conversa sem agentes → linha da Sora;
  // agente independente (avulso, fora de qualquer equipe) → linha solta
  const nascidos = (ids: string[]) => ids.map(id => e.agentes[id]).filter((a): a is AgenteSora => !!a && a.criadoEm <= agora);
  const grupos: { t: number; k: string; el: JSX.Element }[] = [];
  for (const p of e.projetos) {
    const ags = nascidos(p.agenteIds);
    if (ags.length || p.agenteIds.length) grupos.push({ t: p.criadoEm, k: `p-${p.id}`, el: <PastaProjeto p={p} agentes={ags} onNavegar={onNavegar} /> });
    else if (p.tipo === 'chat') grupos.push({ t: p.criadoEm, k: `c-${p.id}`, el: <LinhaChat p={p} onNavegar={onNavegar} /> });
  }
  const naEquipe = new Set(e.projetos.flatMap(p => p.agenteIds));
  for (const a of Object.values(e.agentes)) {
    if (!naEquipe.has(a.id) && a.criadoEm <= agora) grupos.push({ t: a.criadoEm, k: `a-${a.id}`, el: <LinhaAgente a={a} onNavegar={onNavegar} /> });
  }
  const itens = grupos.sort((x, y) => y.t - x.t);
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

/** Identidade e ações da conta, compartilhadas pela Sidebar e pelo menu móvel. */
export function ContaRodape({ onNavegar, movel = false }: { onNavegar?: () => void; movel?: boolean }) {
  const [conta, setConta] = useState(false);
  const contaRef = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();
  const { usuario } = useSessao();
  const nome = usuario?.nome || 'Sua conta';
  const email = usuario?.email ?? '';

  const encerrar = () => {
    onNavegar?.();
    novoChat();
    void sair().then(() => navigate('/'));
  };

  return (
      <div className={`account ${movel ? 'mobile-account' : ''}`}>
        <span className="account-avatar" aria-hidden="true">{nome.slice(0, 1).toUpperCase()}</span>
        <span><strong title={nome}>{nome}</strong><small title={email}>{email}</small></span>
        <NavLink to="/configuracoes" className="account-settings" aria-label="Configurações" title="Configurações" onClick={onNavegar}><GearIcon /></NavLink>
        {movel
          ? <button className="account-logout" type="button" onClick={encerrar}>Sair</button>
          : <>
              <button ref={contaRef} type="button" aria-label="Abrir menu da conta" aria-haspopup="menu" aria-expanded={conta} onClick={() => setConta(v => !v)}>•••</button>
              <AccountMenu open={conta} onClose={() => setConta(false)} anchorRef={contaRef} empresa={nome} plano={email}
                onSelect={a => { if (a === 'plugins') navigate('/plugins'); if (a === 'configuracoes') navigate('/configuracoes'); if (a === 'sair') encerrar(); }} />
            </>}
      </div>
  );
}

export function Sidebar() {
  const { sora } = useProjetos();
  return (
    <aside className="sidebar" aria-label="Navegação principal">
      <NavLink to="/" className="brand" aria-label="Sora, novo chat" onClick={() => novoChat()}>
        <SoraOrb size={22} color={sora.cor} glow={false} decorative seed={3} /><span>Sora</span>
      </NavLink>
      <div className="sidebar-scroll"><Navegacao /></div>
      <IndicadorCreditos />
      <ContaRodape />
    </aside>
  );
}
