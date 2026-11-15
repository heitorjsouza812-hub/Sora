import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { sair, useSessao } from '../../state/sessao';
import { useBots, useSoraId } from '../../state/bots';
import { novoChat, useAgora, useProjetos } from '../../state/projetos';
import { carregarGrupos, useGrupos } from '../../state/grupos';
import { carregarPrecisaDeVoce, usePrecisaDeVoce } from '../../state/atencao';
import { SoraOrb } from '../mascot';
import { NovoGrupo } from '../grupos/NovoGrupo';
import { Popover } from '../overlay';
import { abrirPaleta, MOD } from '../comandos';
import { AgentsIcon, GearIcon, PlusIcon, TeamIcon } from '../ui/Icons';
import { estadoDaMarca, statusDaSora } from './useSoraStatus';

const ClientesIcone = () => <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8.5" r="3.5" /><path d="M5 19.5c.8-3.4 3.5-5 7-5s6.2 1.6 7 5" /></svg>;
const BuscaIcone = () => <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.8" cy="10.8" r="6.3" /><path d="m16 16 4 4" /></svg>;

const pedidos = (n: number) => `${n} ${n === 1 ? 'pedido' : 'pedidos'}`;

/** Contador branco de "Precisa de você" (linhas de bot e de grupo). */
function Contador({ n }: { n: number }) {
  return <b className="shell-contador" role="img" aria-label={`Precisa de você, ${pedidos(n)}`}>{n}</b>;
}

/** Linha da marca: só o mascote e o nome. O estado aparece (ponto discreto) apenas quando a Sora trabalha ou espera por você. */
export function MarcaSora({ onNavegar }: { onNavegar?: () => void }) {
  const e = useProjetos();
  const agora = useAgora();
  const atencao = usePrecisaDeVoce();
  const soraId = useSoraId();
  const status = statusDaSora(e, agora);
  const deSora = atencao.lista.filter(p => !p.grupoId && (!p.botId || p.botId === soraId)).length;
  const estado = estadoDaMarca(status, deSora);
  return <NavLink to="/" end onClick={onNavegar} className="shell-marca" aria-label="Conversar com a Sora">
    <SoraOrb size={28} color="#E2ECFF" glow={false} decorative seed={3} state={estado?.tipo === 'trabalhando' ? status.orb : 'idle'} pulseKey={status.pulso} />
    <strong>Sora</strong>
    <span className="shell-marca-estado" role="status">{estado && <><i className={`shell-ponto is-${estado.tipo}`} title={estado.texto} aria-hidden="true" /><span className="sr-only">{estado.texto}</span></>}</span>
  </NavLink>;
}

// A Sora lidera todo grupo e vem em membros[0]; a contagem de bots vai no title da linha do grupo.
function rotuloBots(grupo: { membros: string[]; liderId?: string | null }): string {
  const lider = grupo.liderId ?? grupo.membros[0];
  const n = grupo.membros.filter(id => id !== lider).length;
  return n === 1 ? '1 bot' : `${n} bots`;
}

export function Navegacao({ onNavegar }: { onNavegar?: () => void }) {
  const navigate = useNavigate();
  const bots = useBots();
  const grupos = useGrupos();
  const atencao = usePrecisaDeVoce();
  const [novoGrupo, setNovoGrupo] = useState(false);
  const [criar, setCriar] = useState(false);
  const criarRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    void carregarGrupos().catch(() => undefined);
    void carregarPrecisaDeVoce().catch(() => undefined);
  }, []);

  // A tela da Sora foca o campo quando chega o sinal em location.state (ver SoraChat).
  const novoBot = () => { setCriar(false); onNavegar?.(); navigate('/bots/novo'); };
  const abrirNovoGrupo = () => { setCriar(false); setNovoGrupo(true); };

  return <>
    <button ref={criarRef} type="button" className="shell-item shell-criar" aria-haspopup="menu" aria-expanded={criar} onClick={() => setCriar(v => !v)}><PlusIcon /><span>Criar novo</span></button>
    <Popover open={criar} onClose={() => setCriar(false)} anchorRef={criarRef} role="menu" ariaLabel="Criar novo" align="start" width={252} className="shell-menu">
      <button type="button" role="menuitem" onClick={novoBot}><AgentsIcon />Novo bot</button>
      <button type="button" role="menuitem" onClick={abrirNovoGrupo}><TeamIcon />Novo grupo</button>
    </Popover>
    <button type="button" className="shell-item shell-buscar" onClick={() => abrirPaleta()}><BuscaIcone /><span>Buscar</span><kbd>{MOD} K</kbd></button>
    <NavLink to="/clientes" onClick={onNavegar} className="shell-item shell-clientes"><ClientesIcone /><span>Clientes</span></NavLink>
    <section className="shell-section" aria-labelledby="nav-bots">
      <header><NavLink id="nav-bots" to="/bots" onClick={onNavegar}>Bots</NavLink><small>{bots.length}</small></header>
      <div className="shell-list">
        {bots.map(bot => {
          const pedidosDoBot = atencao.porBot[bot.id] ?? (bot.estado === 'precisa_de_voce' ? 1 : 0);
          const estado = pedidosDoBot > 0 ? 'precisa_de_voce' : bot.estado;
          return <NavLink key={bot.id} to={`/bots/${bot.id}`} onClick={onNavegar} className="shell-row" style={{ '--agent': bot.cor } as CSSProperties}>
            <SoraOrb size={24} color={bot.cor} glow={false} decorative seed={bot.nome.length} state={estado === 'trabalhando' ? 'working' : 'idle'} />
            <strong title={bot.nome}>{bot.nome}</strong>
            {pedidosDoBot > 0 ? <Contador n={pedidosDoBot} />
              : estado === 'trabalhando' ? <><i className="shell-ponto is-trabalhando" title="Trabalhando" aria-hidden="true" /><span className="sr-only">Trabalhando</span></> : null}
          </NavLink>;
        })}
        {!bots.length && <p className="shell-empty">Peça à Sora para criar seu primeiro bot.</p>}
      </div>
    </section>
    <section className="shell-section" aria-labelledby="nav-grupos">
      <header><NavLink id="nav-grupos" to="/grupos" onClick={onNavegar}>Grupos</NavLink><button type="button" aria-label="Criar grupo" title="Criar grupo" onClick={() => setNovoGrupo(true)}><PlusIcon /></button></header>
      <div className="shell-list">
        {grupos.lista.map(grupo => {
          const pedidosDoGrupo = atencao.porGrupo[grupo.id] ?? (grupo.precisaDeVoce ? 1 : 0);
          return <NavLink key={grupo.id} to={`/grupos/${grupo.id}`} onClick={onNavegar} className="shell-row shell-group" title={`${grupo.nome} · Sora + ${rotuloBots(grupo)}`}>
            <TeamIcon className="shell-group-icon" /><strong>{grupo.nome}</strong>
            {pedidosDoGrupo > 0 ? <Contador n={pedidosDoGrupo} />
              : grupo.trabalhando ? <><i className="shell-ponto is-trabalhando" title="Trabalhando" aria-hidden="true" /><span className="sr-only">Trabalhando</span></> : null}
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
  // O e-mail não aparece aqui: fica em Configurações → Conta.
  return <div className={`account shell-account ${movel ? 'mobile-account' : ''}`}><span className="account-avatar" aria-hidden="true">{nome.slice(0, 1).toUpperCase()}</span><span><strong title={nome}>{nome}</strong></span><NavLink to="/configuracoes" className="account-settings" aria-label="Configurações" title="Configurações" onClick={onNavegar}><GearIcon /></NavLink><button className="account-logout shell-logout" type="button" onClick={encerrar}>Sair</button></div>;
}

export function Sidebar() {
  return <aside className="sidebar shell-sidebar" aria-label="Navegação principal"><MarcaSora /><div className="sidebar-scroll"><Navegacao /></div><ContaRodape /></aside>;
}
