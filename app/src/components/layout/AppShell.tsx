// Moldura do app: barra lateral + cabeçalho (identidade + ações). A navegação é pela barra lateral.
import { useState, type CSSProperties, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { estadoAgente, useAgora, useProjetos } from '../../state/projetos';
import { SoraOrb } from '../mascot';
import { Button, IconButton, toast } from '../base';
import { BottomSheet } from '../overlay';
import { GestaoHost } from '../gestao';
import { Comandos } from '../comandos';
import { Ilha } from '../ilha';
import { FaixaSemConexao } from '../erros';
import { EditorAgenteHost, MenuAgente } from '../builder';
import { ContaRodape, Navegacao, Sidebar } from './Sidebar';
import { statusDaSora } from './useSoraStatus';

export interface AppShellProps {
  children: ReactNode;
  /** quem aparece no cabeçalho: a Sora (padrão), um agente, ou só um título */
  agenteId?: string;
  titulo?: string;
  /** ações à direita da tela (o Compartilhar aparece sozinho em chat, projeto e revisão) */
  acoes?: ReactNode;
  /** itens extras do menu "…" da identidade */
  menuItens?: { rotulo: string; onClick: () => void }[];
}

function Compartilhar() {
  return (
    <Button variante="secundario" tamanho="P" className="share-button" onClick={() => {
      void navigator.clipboard?.writeText(window.location.href).catch(() => {});
      toast({ mensagem: 'Link copiado', tom: 'sucesso' });
    }}>Compartilhar</Button>
  );
}

/** "Compartilhar" só faz sentido onde há algo para mostrar: chats, projetos e revisões. */
const compartilhavel = (caminho: string) => /^\/(projeto|chat|revisao)\//.test(caminho);

function Identidade({ agenteId, titulo, menuItens }: Pick<AppShellProps, 'agenteId' | 'titulo' | 'menuItens'>) {
  const e = useProjetos();
  const agora = useAgora();
  if (titulo) return <div className="topbar-identity topbar-title"><span className="mobile-brand" aria-hidden="true"><SoraOrb size={22} color={e.sora.cor} glow={false} decorative seed={3} /></span><strong>{titulo}</strong></div>;
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
  const { pathname } = useLocation();
  const share = compartilhavel(pathname);
  return (
    <div className="app-shell">
      <Sidebar />
      <section className="app-stage">
        <header className="topbar">
          <IconButton className="mobile-menu-button" variante="secundario" aria-label="Abrir menu" aria-expanded={menu} onClick={() => setMenu(true)}
            icone={<svg viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h16" /></svg>} />
          <Identidade agenteId={agenteId} titulo={titulo} menuItens={menuItens} />
          {(acoes || share) && <div className="topbar-actions">{acoes}{share && <Compartilhar />}</div>}
        </header>
        <FaixaSemConexao />
        {children}
      </section>
      <BottomSheet open={menu} onClose={() => setMenu(false)} title="Menu" className="mobile-nav-sheet">
        <div className="mobile-nav">
          <Navegacao onNavegar={() => setMenu(false)} />
          <ContaRodape movel onNavegar={() => setMenu(false)} />
        </div>
      </BottomSheet>
      <EditorAgenteHost />
      <GestaoHost />
      <Comandos />
      <Ilha />
    </div>
  );
}
