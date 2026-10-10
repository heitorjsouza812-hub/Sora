// Toasts: fila global, região aria-live sempre montada (anúncio confiável), auto-fechar que pausa no
// hover/foco, ação opcional (ex.: "Desfazer"). Não rouba o foco nem bloqueia a tela.
//   <ToastProvider>{app}</ToastProvider>    → monta a região uma vez (raiz do app)
//   const { mostrar } = useToast(); mostrar({ mensagem: 'Projeto apagado', acao: { rotulo: 'Desfazer', onClick } })
//   toast({...}) também funciona fora de componentes (ex.: depois de uma ação do store).
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { fecharToast, novoDono, registrarDono, useDonoToasts, useFilaToasts, type ToastItem } from './toastStore';
import './base.css';

const VISIVEIS = 3;

function ItemToast({ t }: { t: ToastItem }) {
  const duracao = t.duracao ?? (t.acao ? 7000 : 5000);
  const restante = useRef(duracao);
  const inicio = useRef(0);
  const timer = useRef(0);
  const pausar = () => { window.clearTimeout(timer.current); restante.current -= Date.now() - inicio.current; };
  const retomar = () => {
    if (!duracao) return;
    inicio.current = Date.now();
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => fecharToast(t.id), Math.max(1200, restante.current));
  };
  useEffect(() => { retomar(); return () => window.clearTimeout(timer.current); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <li className={`b-toast b-toast--${t.tom ?? 'neutro'}`} onMouseEnter={pausar} onMouseLeave={retomar} onFocus={pausar} onBlur={retomar}>
      <i className="b-toast__ponto" aria-hidden="true" />
      <div className="b-toast__texto">
        <strong>{t.mensagem}</strong>
        {t.descricao && <span>{t.descricao}</span>}
      </div>
      {t.acao && (
        <button type="button" className="b-toast__acao" onClick={() => { t.acao!.onClick(); fecharToast(t.id); }}>{t.acao.rotulo}</button>
      )}
      <button type="button" className="b-toast__fechar" aria-label="Fechar aviso" onClick={() => fecharToast(t.id)}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
      </button>
    </li>
  );
}

/** Região de toasts. Monte na raiz; `children` é opcional (pode envolver o app ou ficar ao lado). */
export function ToastProvider({ children }: { children?: ReactNode }) {
  const [eu] = useState(novoDono);
  useEffect(() => registrarDono(eu), [eu]);
  const dono = useDonoToasts();
  const itens = useFilaToasts();
  if (dono !== eu) return <>{children}</>;
  const visiveis = itens.slice(-VISIVEIS);
  const comuns = visiveis.filter((t) => t.tom !== 'erro');
  const erros = visiveis.filter((t) => t.tom === 'erro');
  return <>
    {children}
    {typeof document !== 'undefined' && createPortal(
      <section className="b-toasts" aria-label="Avisos">
        <div role="status" aria-live="polite" aria-relevant="additions"><ol>{comuns.map((t) => <ItemToast key={t.id} t={t} />)}</ol></div>
        <div role="alert" aria-live="assertive" aria-relevant="additions"><ol>{erros.map((t) => <ItemToast key={t.id} t={t} />)}</ol></div>
      </section>,
      document.body,
    )}
  </>;
}
