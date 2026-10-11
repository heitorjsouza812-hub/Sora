// Compositor grande da tela Projetos: a Sora ouve enquanto o usuário escreve (BorderBeam),
// pensa depois do envio (VoiceBeam em "processing") e monta a equipe. O texto fica com a tela
// (modelos do estado vazio e ?pedido= também preenchem o campo).
import { useState } from 'react';
import { SoraOrb } from '../mascot';
import { MessageComposer } from '../ui/MessageComposer';
import { MODELOS_PROJETO } from './modelos';
import { ID_COMPOSITOR } from './util';

export interface CompositorProjetoProps {
  nomeSora: string;
  corSora: string;
  texto: string;
  onTexto: (texto: string) => void;
  /** true depois do envio: a Sora está pensando */
  pensando: boolean;
  onEnviar: (pedido: string) => void;
}

export function CompositorProjeto({ nomeSora, corSora, texto, onTexto, pensando, onEnviar }: CompositorProjetoProps) {
  const [ouvindo, setOuvindo] = useState(false);
  return (
    <section className="pj-novo" id={ID_COMPOSITOR} aria-labelledby="pj-novo-titulo">
      <div className="pj-novo-cabeca">
        <SoraOrb size={56} color={corSora} glow={false} seed={11}
          state={pensando ? 'thinking' : ouvindo ? 'listening' : 'idle'} lookAt={ouvindo ? { x: 0.2, y: 0.8 } : null}
          title={pensando ? `${nomeSora} pensando` : ouvindo ? `${nomeSora} ouvindo` : `${nomeSora} pronta`} />
        <div>
          <h2 id="pj-novo-titulo">Novo projeto</h2>
          <p role="status" aria-live="polite">{pensando
            ? <span className="sora-shimmer">{nomeSora} está montando o plano e a equipe…</span>
            : `Descreva o resultado que você quer. A ${nomeSora} divide em tarefas e cria um agente para cada uma.`}</p>
        </div>
      </div>
      <MessageComposer
        placeholder={`Descreva o projeto e a ${nomeSora} monta a equipe…`}
        tools
        value={texto}
        onValueChange={onTexto}
        processing={pensando}
        onActivity={setOuvindo}
        onSend={pensando ? undefined : onEnviar}
      />
      <div className="suggestions pj-sugestoes" role="group" aria-label="Sugestões de projeto">
        {MODELOS_PROJETO.slice(0, 4).map((m) => (
          <button type="button" key={m.id} disabled={pensando} onClick={() => onTexto(m.pedido)}>{m.rotulo}</button>
        ))}
      </div>
    </section>
  );
}
