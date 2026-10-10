import { useEffect, useRef, useState } from 'react';
import { agenteDeDescricao, type RascunhoAgente } from '../../data/planejador';
import { lerEstado } from '../../state/projetos';
import { SoraThinking } from '../mascot';
import { MessageComposer } from '../ui/MessageComposer';

/** "Descreva o agente que você quer…": a Sora pensa e preenche o formulário (simulado). */
export function CriarPorDescricao({ onPreencher }: { onPreencher: (r: RascunhoAgente) => void }) {
  const [pensando, setPensando] = useState(false);
  const timer = useRef(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const enviar = (texto: string) => {
    setPensando(true);
    timer.current = window.setTimeout(() => {
      const e = lerEstado();
      const ags = Object.values(e.agentes);
      onPreencher(agenteDeDescricao(texto, { nomesEmUso: ags.map(a => a.nome), coresEmUso: ags.map(a => a.cor) }));
      setPensando(false);
    }, 1700);
  };
  return (
    <div className="st-describe">
      <MessageComposer placeholder="Descreva o agente que você quer…" compact onSend={enviar} processing={pensando} />
      <div className="st-describe-status" aria-live="polite">
        {pensando ? <SoraThinking label="Sora está montando o agente…" size={24} /> : <small>Ex.: “um agente que escreve legendas divertidas para o Instagram”</small>}
      </div>
    </div>
  );
}
