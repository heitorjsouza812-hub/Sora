import { useEffect, useState, type CSSProperties } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { sair, useSessao } from '../../state/sessao';
import { useBots } from '../../state/bots';
import { novoChat } from '../../state/projetos';
import { carregarGrupos, useGrupos } from '../../state/grupos';
import { carregarPrecisaDeVoce, usePrecisaDeVoce } from '../../state/atencao';
import { SoraOrb } from '../mascot';
import { NovoGrupo } from '../grupos/NovoGrupo';
import { abrirPaleta } from '../comandos';
import { GearIcon, PlusIcon, TeamIcon } from '../ui/Icons';

const BuscaIcone = () => <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.8" cy="10.8" r="6.3" /><path d="m16 16 4 4" /></svg>;
// A Sora lidera todo grupo e vem em membros[0]; a contagem mostra só os bots.
function rotuloBots(grupo: { membros: string[]; liderId?: string | null }): string {
  const lider = grupo.liderId ?? grupo.membros[0];
  const n = grupo.membros.filter(id => id !== lider).length;
  return n === 1 ? '1 bot' : `${n} bots`;
}
const rotuloEstado =(estado: 'livre' | 'trabalhando' | 'precisa_de_voce') => estado === 'precisa_de_voce' ? 'Precisa de você' : estado === 'trabalhando' ? 'Trabalhando' : 'Livre';

export function Navegacao({ onNavegar }: { onNavegar?: () => void }) {
  const navigate = useNavigate();
  const bots = useBots();
  const grupos = useGrupos();
  const atencao = usePrecisaDeVoce();
  const [novoGrupo, setNovoGrupo] = useState(false);

  useEffect(() => {
    void carregarGrupos().catch(() => undefined);
    void carregarPrecisaDeVoce().catch(() => undefined);
  }, []);

  return <>
    <button type="button" className="shell-search" onClick={() => abrirPaleta()}><BuscaIcone /><span>Buscar</span><kbd>Ctrl K</kbd></button>
    <section className="shell-section" aria-labelledby="nav-bots">
      <header><NavLink id="nav-bots" to="/bots" onClick={onNavegar}>Bots</NavLink><small>{bots.length}</small></header>
      <div className="shell-list">
        {bots.map(bot => {
          const estado = (atencao.porBot[bot.id] ?? 0) > 0 ? 'precisa_de_voce' : bot.estado;
          return <NavLink key={bot.id} to={`/bots/${bot.id}`} onClick={onNavegar} className="shell-row" style={{ '--agent': bot.cor } as CSSProperties}>
            <SoraOrb size={30} color={bot.cor} glow={false} decorative seed={bot.nome.length} state={estado === 'trabalhando' ? 'working' : 'idle'} />
            <span><strong>{bot.nome}</strong><small className={`shell-state is-${estado}`}>{rotuloEstado(estado)}</small></span><i className={`shell-dot is-${estado}`} aria-hidden="true" />
          </NavLink>;
        })}
        {!bots.length && <p className="shell-empty">Peça à Sora para criar seu primeiro bot.</p>}
      </div>
    </section>
    <section className="shell-section" aria-labelledby="nav-grupos">
      <header><NavLink id="nav-grupos" to="/grupos" onClick={onNavegar}>Grupos</NavLink><button type="button" aria-label="Criar grupo" title="Criar grupo" onClick={() => setNovoGrupo(true)}><PlusIcon /></button></header>
      <div className="shell-list">
        {grupos.lista.map(grupo => {
          const precisa = grupo.precisaDeVoce || (atencao.porGrupo[grupo.id] ?? 0) > 0;
          return <NavLink key={grupo.id} to={`/grupos/${grupo.id}`} onClick={onNavegar} className={`shell-row shell-group ${precisa ? 'needs-you' : ''}`}>
            <span className="shell-group-icon"><TeamIcon /></span><span><strong>{grupo.nome}</strong><small>{precisa ? 'Precisa de você' : grupo.trabalhando ? 'Trabalhando' : rotuloBots(grupo)}</small></span>{precisa && <i className="shell-attention" aria-label="Precisa de você">!</i>}
          </NavLink>;
        })}
      </div>
    </section>
    <NovoGrupo aberto={novoGrupo} onFechar={() => setNovoGrupo(false)} onCriado={id => { setNovoGrupo(false); onNavegar?.(); navigate(`/grupos/${id}`); }} />
  </>;
}

export function ContaRodape({ onNavegar, movel = false }: { onNavegar?: () => void; movel?: boolean }) {
  const navigate = useNavigate();
  const { usuario } = useSessao();
  const nome = usuario?.nome || 'Sua conta';
  const encerrar = () => { onNavegar?.(); novoChat(); void sair().then(() => navigate('/')); };
  return <div className={`account shell-account ${movel ? 'mobile-account' : ''}`}><span className="account-avatar" aria-hidden="true">{nome.slice(0, 1).toUpperCase()}</span><span><strong title={nome}>{nome}</strong><small title={usuario?.email ?? ''}>{usuario?.email ?? ''}</small></span><NavLink to="/configuracoes" className="account-settings" aria-label="Configurações" title="Configurações" onClick={onNavegar}><GearIcon /></NavLink><button className="account-logout shell-logout" type="button" onClick={encerrar}>Sair</button></div>;
}

export function Sidebar() {
  return <aside className="sidebar shell-sidebar" aria-label="Navegação principal"><NavLink to="/" className="brand shell-sora" aria-label="Conversar com a Sora"><SoraOrb size={30} color="#E2ECFF" glow={false} decorative seed={3} state="idle" /><span><strong>Sora</strong><small>Chefe de equipe</small></span></NavLink><div className="sidebar-scroll"><Navegacao /></div><ContaRodape /></aside>;
}
