// Novo chat: a Sora grande acima de "Em que posso te ajudar hoje?" (como na demo).
// Chegada (~1,6 s, só na 1ª abertura da sessão) → ocioso; ouvindo (olha para o campo) ao digitar ou
// com o microfone ao vivo; ao enviar: pensando + pulso, encolhe e vai para a conversa.
// A barra lateral continua vazia até o primeiro envio.
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { SoraOrb } from '../components/mascot';
import { MessageComposer } from '../components/ui/MessageComposer';
import { anexarEnvio, criarProjeto, novoChat, useProjetos } from '../state/projetos';
import type { Anexo } from '../components/anexos';

const sugestoes: [string, string][] = [
  ['Criar campanha', 'Crie uma campanha para lançar minha cafeteria: pesquise referências, prepare as peças e monte um calendário de posts.'],
  ['Pesquisar mercado', 'Faça uma pesquisa de mercado sobre cafeterias no meu bairro, com concorrentes e preços.'],
  ['Planejar posts', 'Planeje os posts do mês para o Instagram da minha loja.'],
  ['Resumir e-mails', 'Resuma meus e-mails da semana e sugira respostas.'],
];

/** A chegada só acontece na primeira abertura da sessão (lido uma vez por carga da página). */
let chegadaPendente = (() => {
  try {
    if (sessionStorage.getItem('sora.chegou')) return false;
    sessionStorage.setItem('sora.chegou', '1');
    return true;
  } catch { return false; }
})();

export default function Home() {
  const [chegando, setChegando] = useState(() => chegadaPendente);
  const [ouvindo, setOuvindo] = useState(false);
  const [enviado, setEnviado] = useState(false);
  const [partindo, setPartindo] = useState(false);
  const [pulso, setPulso] = useState(0);
  const [texto, setTexto] = useState('');
  const timers = useRef<number[]>([]);
  const navigate = useNavigate();
  const { sora } = useProjetos();

  useEffect(() => { chegadaPendente = false; novoChat(); }, []);
  useEffect(() => () => timers.current.forEach((t) => window.clearTimeout(t)), []);

  const enviar = (pedido: string, anexos: Anexo[] = []) => {
    if (enviado) return;
    setEnviado(true);
    setOuvindo(false);
    setPulso((p) => p + 1);
    timers.current = [
      window.setTimeout(() => setPartindo(true), 650),
      window.setTimeout(() => {
        // a conversa (e o item em CHATS) só nasce agora, junto com a ida para o chat
        const p = anexarEnvio(anexos, () => criarProjeto(pedido, undefined, { tipo: 'chat' }));
        navigate(`/projeto/${p.id}`);
      }, 1150),
    ];
  };

  const estado = enviado ? 'thinking' : chegando ? 'arriving' : ouvindo ? 'listening' : 'idle';

  return (
    <AppShell titulo="Novo chat" acoes={<span />}>
      <main className="home-screen">
        <div className={`hero-orb ${partindo ? 'orb-departing' : ''}`}>
          <SoraOrb
            size={260}
            color={sora.cor}
            state={estado}
            lookAt={ouvindo ? { x: -0.1, y: 0.85 } : null}
            pulseKey={pulso}
            seed={0}
            onArrived={() => setChegando(false)}
            title={enviado ? `${sora.nome} pensando` : `${sora.nome} pronta para ajudar`}
          />
        </div>
        <h1>Em que posso te ajudar hoje?</h1>
        <div className="hero-composer">
          <MessageComposer
            placeholder={`Peça qualquer coisa à ${sora.nome}…`}
            tools
            value={texto}
            onValueChange={setTexto}
            processing={enviado}
            onActivity={(ativo) => { if (!enviado) setOuvindo(ativo); }}
            onSend={enviar}
          />
        </div>
        <div className="suggestions" aria-label="Sugestões">
          {sugestoes.map(([rotulo, pedido]) => <button type="button" key={rotulo} onClick={() => setTexto(pedido)}>{rotulo}</button>)}
        </div>
      </main>
    </AppShell>
  );
}
