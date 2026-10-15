// Vista Aprovação: o "Allow/Deny" do Coucou adaptado à regra "nada é publicado sem a sua aprovação".
// Atalhos N (pedir ajuste), R (revisar) e Y (aprovar) valem com a ilha aberta e foco fora de campos.
import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { SoraOrb } from '../mascot';
import { toast } from '../base';
import { aprovarProjeto, useProjetos } from '../../state/projetos';
import type { AlertaIlha } from './ilhaEstado';
import { useIlhaPrefs } from './ilhaEstado';
import { tocar } from './som';

export interface AprovacaoProps {
  alerta: AlertaIlha;
  /** chamado depois de qualquer ação (a ilha fecha) */
  onFeito: () => void;
}

const digitando = (el: EventTarget | null) => {
  const h = el as HTMLElement | null;
  return !!h && (h.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(h.tagName));
};

export function Aprovacao({ alerta, onFeito }: AprovacaoProps) {
  const navigate = useNavigate();
  const e = useProjetos();
  const { som } = useIlhaPrefs();
  const ref = useRef<HTMLDivElement>(null);

  const revisar = () => { navigate(`/revisao/${alerta.projetoId}`); onFeito(); };
  const aprovar = () => {
    aprovarProjeto(alerta.projetoId);
    if (som) tocar('aprovado');
    toast({ mensagem: 'Projeto aprovado e publicado', descricao: alerta.titulo, tom: 'sucesso' });
    onFeito();
  };

  const acoes = useRef({ revisar, aprovar });
  useEffect(() => { acoes.current = { revisar, aprovar }; });

  useEffect(() => {
    // a janela destacada (Picture-in-Picture) tem o próprio window
    const janela = ref.current?.ownerDocument.defaultView ?? window;
    const tecla = (ev: KeyboardEvent) => {
      if (ev.ctrlKey || ev.metaKey || ev.altKey || digitando(ev.target)) return;
      const k = ev.key.toLowerCase();
      if (k === 'n' || k === 'r') { ev.preventDefault(); acoes.current.revisar(); }
      else if (k === 'y') { ev.preventDefault(); acoes.current.aprovar(); }
    };
    janela.addEventListener('keydown', tecla);
    return () => janela.removeEventListener('keydown', tecla);
  }, []);

  return (
    <div ref={ref} className="ilha-aprovacao">
      <SoraOrb size={72} color={e.sora.cor} state="done" pulseKey={1} glow decorative seed={13} />
      <div className="ilha-aprovacao-texto">
        <p className="ilha-sora-titulo">
          <span className="ilha-ponto ilha-ponto--ok" aria-hidden="true" />
          <span>A equipe terminou <strong>{alerta.titulo}</strong></span>
        </p>
        {alerta.entregas.length > 0 && (
          <ul className="ilha-entregas">
            {alerta.entregas.map(en => <li key={en}>{en}</li>)}
          </ul>
        )}
        <p className="ilha-aviso">Nada é publicado sem a sua aprovação.</p>
        <div className="ilha-aprovacao-botoes">
          <button type="button" className="ilha-btn" onClick={revisar} aria-keyshortcuts="N">Pedir ajuste <kbd>N</kbd></button>
          <button type="button" className="ilha-btn" onClick={revisar} aria-keyshortcuts="R">Revisar <kbd>R</kbd></button>
          <button type="button" className="ilha-btn ilha-btn--primario" onClick={aprovar} aria-keyshortcuts="Y">Aprovar e publicar <kbd>Y</kbd></button>
        </div>
      </div>
    </div>
  );
}

export default Aprovacao;
