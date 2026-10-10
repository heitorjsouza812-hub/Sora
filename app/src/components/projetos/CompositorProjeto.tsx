// Compositor grande da tela Projetos: a Sora ouve enquanto o usuário escreve (BorderBeam),
// pensa depois do envio (VoiceBeam em "processing") e monta a equipe.
import { useState } from 'react';
import { SoraOrb } from '../mascot';
import { MessageComposer } from '../ui/MessageComposer';

const SUGESTOES: [string, string][] = [
  ['Campanha de lançamento', 'Crie uma campanha de lançamento para minha cafeteria: pesquise referências, prepare as peças e monte um calendário de posts.'],
  ['Landing page', 'Monte uma landing page para o meu curso online: estrutura das seções, textos persuasivos e visual das telas.'],
  ['Pesquisa de mercado', 'Faça uma pesquisa de mercado sobre academias no meu bairro, com concorrentes, preços e oportunidades.'],
  ['Roteiro de vídeo', 'Escreva o roteiro de um vídeo de 60 segundos para o Instagram apresentando a minha loja, com cenas e legendas.'],
];

export interface CompositorProjetoProps {
  nomeSora: string;
  corSora: string;
  /** true depois do envio: a Sora está pensando */
  pensando: boolean;
  onEnviar: (pedido: string) => void;
}

export function CompositorProjeto({ nomeSora, corSora, pensando, onEnviar }: CompositorProjetoProps) {
  const [texto, setTexto] = useState('');
  const [ouvindo, setOuvindo] = useState(false);
  return (
    <section className="pj-novo" aria-labelledby="pj-novo-titulo">
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
        onValueChange={setTexto}
        processing={pensando}
        onActivity={setOuvindo}
        onSend={pensando ? undefined : onEnviar}
      />
      <div className="suggestions pj-sugestoes" role="group" aria-label="Sugestões de projeto">
        {SUGESTOES.map(([rotulo, pedido]) => (
          <button type="button" key={rotulo} disabled={pensando} onClick={() => setTexto(pedido)}>{rotulo}</button>
        ))}
      </div>
    </section>
  );
}
