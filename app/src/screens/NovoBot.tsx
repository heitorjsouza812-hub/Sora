import { useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { SoraOrb, SoraThinking } from '../components/mascot';
import { MessageComposer } from '../components/ui/MessageComposer';
import { criarBotPorDescricao } from '../api/bots';
import { mensagemDeErro } from '../api/cliente';
import { adicionarBot } from '../state/bots';
import { registrarBot, enviarParaAgente } from '../state/projetos';

function Formulario() {
  const navigate = useNavigate();
  const [texto, setTexto] = useState('');
  const [erro, setErro] = useState('');
  const [criando, setCriando] = useState(false);
  const ocupado = useRef(false);
  async function enviar(pedido: string) {
    if (ocupado.current) return;
    ocupado.current = true;
    setCriando(true); setErro('');
    try {
      const bot = await criarBotPorDescricao(pedido);
      adicionarBot(bot); registrarBot(bot);
      navigate(`/bots/${bot.id}`);
      void enviarParaAgente(bot.id, pedido);
    } catch (e) {
      setTexto(pedido); setErro(mensagemDeErro(e));
    } finally { ocupado.current = false; setCriando(false); }
  }
  return <main className="novo-bot"><SoraOrb size={112} state="idle" />
    <h1>Que bot você quer criar?</h1>
    {criando ? <div role="status"><SoraThinking size={40} label="Criando seu bot…" /></div>
      : <div className="novo-bot-composer"><MessageComposer grande placeholder="Descreva o bot que você quer criar…" value={texto}
          onValueChange={setTexto} onSend={enviar} anexar={false} /></div>}
    {erro && <p role="alert">{erro}</p>}
  </main>;
}
export default function NovoBot() {
  const location = useLocation();
  return <AppShell><Formulario key={location.key} /></AppShell>;
}
