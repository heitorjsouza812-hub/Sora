import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { SoraOrb } from '../components/mascot';
import { MessageComposer } from '../components/ui/MessageComposer';
import { PEDIDO_CAMPANHA } from '../data/mock';
import { useSora } from '../state/SoraContext';

const sugestoes = ['Criar campanha', 'Pesquisar mercado', 'Planejar posts', 'Resumir e-mails'];

export default function Home() {
  const [chegando, setChegando] = useState(true);
  const [ouvindo, setOuvindo] = useState(false);
  const [partindo, setPartindo] = useState(false);
  const { enviar, dispatch, state } = useSora();
  const navigate = useNavigate();
  useEffect(() => {
    const timer = window.setTimeout(() => setChegando(false), 2800);
    return () => window.clearTimeout(timer);
  }, []);

  const handleSend = (pedido: string) => {
    enviar(pedido);
    setOuvindo(false);
    window.setTimeout(() => setPartindo(true), 600);
    window.setTimeout(() => navigate('/chat/sora'), 1180);
  };

  const heroState = state.fase === 'enviado' ? 'thinking' : chegando ? 'arriving' : ouvindo ? 'listening' : 'idle';

  return (
    <AppShell title="Novo chat">
      <main className="home-screen">
        <div className={`hero-orb ${partindo ? 'orb-departing' : ''}`}>
          <SoraOrb
            size={260}
            state={heroState}
            lookAt={ouvindo ? { x: 0, y: .8 } : null}
            pulseKey={state.pulseKey}
            seed={0}
            onArrived={() => setChegando(false)}
            title={state.fase === 'enviado' ? 'Sora pensando' : 'Sora pronta para ajudar'}
          />
        </div>
        <h1>Em que posso te ajudar hoje?</h1>
        <div className="hero-composer">
          <MessageComposer
            placeholder="Peça qualquer coisa à Sora…"
            tools
            onActivity={(active) => { setOuvindo(active); dispatch({ type: 'OUVIR', ativo: active }); }}
            onSend={handleSend}
          />
        </div>
        <div className="suggestions" aria-label="Sugestões">
          {sugestoes.map((sugestao) => <button key={sugestao} onClick={() => handleSend(sugestao === 'Criar campanha' ? PEDIDO_CAMPANHA : sugestao)}>{sugestao}</button>)}
        </div>
      </main>
    </AppShell>
  );
}

