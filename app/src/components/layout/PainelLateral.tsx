// Painel direito ÚNICO com abas (ex.: Equipe | Trabalho | Entregas), recolhível por botão ou Ctrl+.
// Lembra a aba e se está recolhido (localStorage, com try/catch). No celular vira BottomSheet com as
// mesmas abas, aberto por uma pílula fixa acima do campo de mensagem.
import { useEffect, useId, type CSSProperties, type KeyboardEvent, type ReactNode } from 'react';
import { IconButton, Tooltip } from '../base';
import { BottomSheet } from '../overlay';
import { useCelular } from '../ui/useMedia';

export interface AbaPainel {
  id: string;
  rotulo: string;
  icone: ReactNode;
  conteudo: ReactNode;
  /** pontinho pulsando na aba (ex.: alguém trabalhando), na cor dada */
  vivo?: string | null;
  /** número discreto ao lado do rótulo (ex.: 3 entregas) */
  contagem?: number;
}

export interface PainelLateralProps {
  abas: AbaPainel[];
  aba: string;
  onAba: (id: string) => void;
  recolhido: boolean;
  onRecolher: (recolhido: boolean) => void;
  /** celular: BottomSheet aberto (controlado pelo pai, para o "Ver trabalho" poder abrir) */
  folhaAberta: boolean;
  onFolha: (aberta: boolean) => void;
  /** resumo curto na pílula do celular (ex.: "Atlas · Pesquisando…") */
  resumo?: string;
  rotulo?: string;
}

const Seta = ({ para }: { para: 'dir' | 'esq' }) => <svg viewBox="0 0 24 24"><path d={para === 'dir' ? 'm9 6 6 6-6 6' : 'm15 6-6 6 6 6'} /></svg>;

export function PainelLateral({ abas, aba, onAba, recolhido, onRecolher, folhaAberta, onFolha, resumo, rotulo = 'Painel do projeto' }: PainelLateralProps) {
  const celular = useCelular();
  const base = useId();
  const atual = abas.find((a) => a.id === aba) ?? abas[0];

  // atalho: Ctrl+. recolhe/expande (Cmd+. no Mac)
  useEffect(() => {
    if (celular) return;
    const tecla = (ev: globalThis.KeyboardEvent) => {
      if ((ev.ctrlKey || ev.metaKey) && ev.key === '.') { ev.preventDefault(); onRecolher(!recolhido); }
    };
    window.addEventListener('keydown', tecla);
    return () => window.removeEventListener('keydown', tecla);
  }, [celular, recolhido, onRecolher]);

  // setas ←/→ (Home/End) trocam de aba, como pede o padrão WAI-ARIA de abas
  const teclaAbas = (ev: KeyboardEvent<HTMLDivElement>) => {
    const i = abas.findIndex((a) => a.id === atual.id);
    const prox = ev.key === 'ArrowRight' ? (i + 1) % abas.length : ev.key === 'ArrowLeft' ? (i - 1 + abas.length) % abas.length
      : ev.key === 'Home' ? 0 : ev.key === 'End' ? abas.length - 1 : -1;
    if (prox < 0) return;
    ev.preventDefault();
    onAba(abas[prox].id);
    document.getElementById(`${base}-tab-${abas[prox].id}`)?.focus();
  };

  const listaAbas = (
    <div className="side-tabs" role="tablist" aria-label={rotulo} onKeyDown={teclaAbas}>
      {abas.map((a) => (
        <button key={a.id} id={`${base}-tab-${a.id}`} type="button" role="tab" aria-selected={a.id === atual.id}
          aria-controls={`${base}-panel`} tabIndex={a.id === atual.id ? 0 : -1}
          className={a.id === atual.id ? 'is-on' : ''} onClick={() => onAba(a.id)}
          style={a.vivo ? { '--agent': a.vivo } as CSSProperties : undefined}>
          {a.vivo && <i className="wk-pulse is-live" aria-hidden="true" />}
          <span>{a.rotulo}</span>
          {!!a.contagem && <small className="side-count">{a.contagem}</small>}
        </button>
      ))}
    </div>
  );
  const conteudo = <div id={`${base}-panel`} role="tabpanel" aria-labelledby={`${base}-tab-${atual.id}`} className="side-body">{atual.conteudo}</div>;

  if (celular) {
    const vivo = abas.find((a) => a.vivo)?.vivo;
    return <>
      <button type="button" className="work-pill" onClick={() => onFolha(true)} aria-haspopup="dialog"
        style={vivo ? { '--agent': vivo } as CSSProperties : undefined}>
        <i className={`wk-pulse ${vivo ? 'is-live' : ''}`} aria-hidden="true" />
        <strong>{abas.map((a) => a.rotulo).join(' · ')}</strong>{resumo && <span>{resumo}</span>}
      </button>
      <BottomSheet open={folhaAberta} onClose={() => onFolha(false)} title={rotulo} className="side-sheet">
        {listaAbas}{conteudo}
      </BottomSheet>
    </>;
  }

  if (recolhido) {
    return (
      <aside className="side-panel is-collapsed" aria-label={rotulo}>
        <Tooltip conteudo="Mostrar painel (Ctrl+.)" lado="baixo">
          <IconButton aria-label="Mostrar painel" aria-expanded={false} icone={<Seta para="esq" />} onClick={() => onRecolher(false)} />
        </Tooltip>
        {abas.map((a) => (
          <Tooltip key={a.id} conteudo={a.rotulo} lado="baixo">
            <IconButton aria-label={`Abrir ${a.rotulo}`} icone={a.icone} className={a.vivo ? 'side-rail-live' : ''}
              style={a.vivo ? { '--agent': a.vivo } as CSSProperties : undefined}
              onClick={() => { onAba(a.id); onRecolher(false); }} />
          </Tooltip>
        ))}
      </aside>
    );
  }

  return (
    <aside className="side-panel card" aria-label={rotulo}>
      <div className="side-head">
        {listaAbas}
        <Tooltip conteudo="Recolher painel (Ctrl+.)" lado="baixo">
          <IconButton aria-label="Recolher painel" aria-expanded icone={<Seta para="dir" />} tamanho="P" onClick={() => onRecolher(true)} />
        </Tooltip>
      </div>
      {conteudo}
    </aside>
  );
}
