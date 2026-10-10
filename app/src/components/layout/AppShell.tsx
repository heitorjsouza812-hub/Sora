// Moldura do app: barra lateral + cabeçalho (identidade + ações). A navegação é pela barra lateral.
import { useState, type CSSProperties, type ReactNode } from 'react';
import { estadoAgente, useAgora, useProjetos } from '../../state/projetos';
import { SoraOrb } from '../mascot';
import { BottomSheet } from '../overlay';
import { GestaoHost } from '../gestao';
import { EditorAgenteHost, MenuAgente } from '../builder';
import { Navegacao, Sidebar } from './Sidebar';
import { statusDaSora } from './useSoraStatus';

export interface AppShellProps {
  children: ReactNode;
  /** quem aparece no cabeçalho: a Sora (padrão), um agente, ou só um título */
  agenteId?: string;
  titulo?: string;
  /** ações à direita (padrão: Compartilhar) */
  acoes?: ReactNode;
  /** itens extras do menu "…" da identidade */
  menuItens?: { rotulo: string; onClick: () => void }[];
}

function Compartilhar() {
  const [ok, setOk] = useState(false);
  return (
    <button type="button" className="share-button" onClick={() => {
      void navigator.clipboard?.writeText(window.location.href).catch(() => {});
      setOk(true); window.setTimeout(() => setOk(false), 1800);
    }}>
      <span aria-live="polite">{ok ? 'Link copiado' : 'Compartilhar'}</span>
    </button>
  );
}

function Identidade({ agenteId, titulo, menuItens }: Pick<AppShellProps, 'agenteId' | 'titulo' | 'menuItens'>) {
  const e = useProjetos();
  const agora = useAgora();
  if (titulo) return <div className="topbar-identity topbar-title"><strong>{titulo}</strong></div>;
  const ag = agenteId ? e.agentes[agenteId] : undefined;
  if (ag) {
    const st = estadoAgente(e, ag.id, agora);
    return (
      <div className="topbar-identity" style={{ '--header-accent': st.status === 'concluido' ? 'var(--ok)' : ag.cor } as CSSProperties}>
        <SoraOrb size={38} color={ag.cor} movimento={ag.tipoMovimento} glow={false} decorative seed={7}
          state={st.status === 'trabalhando' ? 'working' : st.status === 'concluido' ? 'done' : 'idle'} />
        <span><strong>{ag.nome}</strong><small role="status"><i />{st.rotulo || ag.funcao}</small></span>
        <MenuAgente agenteId={ag.id} nome={ag.nome} itens={menuItens} />
      </div>
    );
  }
  const s = statusDaSora(e, agora);
  return (
    <div className="topbar-identity" style={{ '--header-accent': s.orb === 'thinking' ? e.sora.cor : 'var(--ok)' } as CSSProperties}>
      <SoraOrb size={38} color={e.sora.cor} state={s.orb} pulseKey={s.pulso} glow={false} decorative seed={9} />
      <span><strong>{e.sora.nome}</strong><small role="status"><i />{s.rotulo}</small></span>
      <MenuAgente agenteId="sora" nome={e.sora.nome} itens={menuItens} />
    </div>
  );
}

export function AppShell({ children, agenteId, titulo, acoes, menuItens }: AppShellProps) {
  const [menu, setMenu] = useState(false);
  return (
    <div className="app-shell">
      <Sidebar />
      <section className="app-stage">
        <header className="topbar">
          <button type="button" className="mobile-menu-button" aria-label="Abrir menu" aria-expanded={menu} onClick={() => setMenu(true)}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" /></svg>
          </button>
          <Identidade agenteId={agenteId} titulo={titulo} menuItens={menuItens} />
          <div className="topbar-actions">{acoes ?? <Compartilhar />}</div>
        </header>
        {children}
      </section>
      <BottomSheet open={menu} onClose={() => setMenu(false)} title="Menu" className="mobile-nav-sheet">
        <div className="mobile-nav"><Navegacao onNavegar={() => setMenu(false)} /></div>
      </BottomSheet>
      <EditorAgenteHost />
      <GestaoHost />
    </div>
  );
}
