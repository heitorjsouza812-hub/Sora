import { PreferenciasDaConversa, SeloAcessoTotal } from '../../state/preferenciasConversa';
// Moldura do app: barra lateral + cabeçalho (identidade + ações). A navegação é pela barra lateral.
import { useEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from 'react';
import { estadoAgente, useAgora, useProjetos } from '../../state/projetos';
import { usePrecisaDeVoce } from '../../state/atencao';
import { SoraOrb } from '../mascot';
import { IconButton } from '../base';
import { BottomSheet } from '../overlay';
import { GestaoHost } from '../gestao';
import { Comandos } from '../comandos';
import { FaixaErroEventos, FaixaSemConexao } from '../erros';
import { EditorAgenteHost, MenuAgente } from '../builder';
import { ContaRodape, MarcaSora, Navegacao, Sidebar } from './Sidebar';
import './etapa5.css';
import './topbar.css';
import '../ui/conversa.css';

export interface AppShellProps {
  children: ReactNode;
  conversaId?: string;
  preferenciasBotId?: string;
  /** quem aparece no cabeçalho: a Sora (padrão), um agente, ou só um título */
  agenteId?: string;
  titulo?: string;
  /** texto de apoio depois do título, em cinza (ex.: "Sora + 2 bots" no grupo) */
  subtitulo?: string;
  /** ações à direita da tela (o Compartilhar aparece sozinho em chat, projeto e revisão) */
  acoes?: ReactNode;
  /** itens extras do menu "…" da identidade */
  menuItens?: { rotulo: string; onClick: () => void }[];
}

/** Estado do bot ao lado do nome: o verbo na cor dele quando trabalha, "Precisa de você" em cinza; disponível = nada. */
function estadoDoBot(trabalhando: boolean, verbo: string, precisa: boolean): { texto: string; precisa: boolean } | null {
  if (precisa) return { texto: 'Precisa de você', precisa: true };
  return trabalhando ? { texto: verbo, precisa: false } : null;
}

/** Esquerda do cabeçalho. Sora em `/`: vazio no desktop (a barra lateral já diz quem ela é); no celular, orb + nome. */
function Identidade({ agenteId, titulo, subtitulo }: Pick<AppShellProps, 'agenteId' | 'titulo' | 'subtitulo'>) {
  const e = useProjetos();
  const agora = useAgora();
  const atencao = usePrecisaDeVoce();
  if (titulo) return <div className="topbar-identity topbar-title"><span className="mobile-brand" aria-hidden="true"><SoraOrb size={22} color={e.sora.cor} glow={false} decorative seed={3} /></span><div className="topbar-linha"><strong className="topbar-nome">{titulo}</strong>{subtitulo && <span className="topbar-sub">· {subtitulo}</span>}</div></div>;
  const ag = agenteId ? e.agentes[agenteId] : undefined;
  if (ag) {
    const st = estadoAgente(e, ag.id, agora);
    const estado = estadoDoBot(st.status === 'trabalhando', ag.verbo, (atencao.porBot[ag.id] ?? 0) > 0);
    return (
      <div className="topbar-identity" style={{ '--header-accent': estado && !estado.precisa ? ag.cor : 'var(--text-2)' } as CSSProperties}>
        <SoraOrb size={28} color={ag.cor} movimento={ag.tipoMovimento} glow={false} decorative seed={7}
          state={st.status === 'trabalhando' ? 'working' : st.status === 'concluido' ? 'done' : 'idle'} />
        <div className="topbar-linha"><strong className="topbar-nome" title={ag.funcao}>{ag.nome}</strong><span className="topbar-estado" role="status">{estado ? `· ${estado.texto}` : ''}</span></div>
      </div>
    );
  }
  return (
    <div className="topbar-identity is-sora">
      <SoraOrb size={22} color={e.sora.cor} glow={false} decorative seed={9} />
      <div className="topbar-linha"><strong className="topbar-nome">{e.sora.nome}</strong></div>
    </div>
  );
}

/** Menu "…" do cabeçalho: do bot ou da Sora (telas com título próprio não têm). */
function MenuDoCabecalho({ agenteId, titulo, menuItens }: Pick<AppShellProps, 'agenteId' | 'titulo' | 'menuItens'>) {
  const e = useProjetos();
  if (titulo) return null;
  const ag = agenteId ? e.agentes[agenteId] : undefined;
  return ag ? <MenuAgente agenteId={ag.id} nome={ag.nome} itens={menuItens} /> : <MenuAgente agenteId="sora" nome={e.sora.nome} itens={menuItens} />;
}

/** A divisória do cabeçalho só aparece quando o conteúdo rola por baixo dele (um rolador que começa logo abaixo do cabeçalho). */
function useDivisoriaAoRolar(cabecalho: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const alvoDe = (ev: Event) => ev.target instanceof HTMLElement ? ev.target : null;
    const aoRolar = (ev: Event) => {
      const topo = cabecalho.current; const el = alvoDe(ev);
      if (!topo || !el || topo.contains(el)) return;
      const abaixo = el.getBoundingClientRect().top <= topo.getBoundingClientRect().bottom + 2;
      if (abaixo) topo.toggleAttribute('data-rolou', el.scrollTop > 2);
    };
    document.addEventListener('scroll', aoRolar, true);
    return () => document.removeEventListener('scroll', aoRolar, true);
  }, [cabecalho]);
}

export function AppShell({ children, agenteId, titulo, subtitulo, acoes, menuItens, conversaId, preferenciasBotId }: AppShellProps) {
  const [menu, setMenu] = useState(false);
  const cabecalho = useRef<HTMLElement>(null);
  useDivisoriaAoRolar(cabecalho);
  return (
    <PreferenciasDaConversa conversaId={conversaId} botId={preferenciasBotId}>
    <div className="app-shell">
      <Sidebar />
      <section className="app-stage">
        <header className="topbar" ref={cabecalho}>
          <IconButton className="mobile-menu-button" variante="secundario" aria-label="Abrir menu" aria-expanded={menu} onClick={() => setMenu(true)}
            icone={<svg viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h16" /></svg>} />
          <Identidade agenteId={agenteId} titulo={titulo} subtitulo={subtitulo} />
          <div className="topbar-actions"><SeloAcessoTotal />{acoes}<MenuDoCabecalho agenteId={agenteId} titulo={titulo} menuItens={menuItens} /></div>
        </header>
        <FaixaSemConexao />
        <FaixaErroEventos />
        {children}
      </section>
      <BottomSheet open={menu} onClose={() => setMenu(false)} title="Menu" className="mobile-nav-sheet">
        <div className="mobile-nav">
          <MarcaSora onNavegar={() => setMenu(false)} />
          <Navegacao onNavegar={() => setMenu(false)} />
          <ContaRodape movel onNavegar={() => setMenu(false)} />
        </div>
      </BottomSheet>
      <EditorAgenteHost />
      <GestaoHost />
      <Comandos />
    </div>
    </PreferenciasDaConversa>
  );
}
