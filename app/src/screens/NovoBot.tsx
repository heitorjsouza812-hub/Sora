import './novoBot.css';
import { AUTOMATICO } from '../api/preferenciasConversa';
import { useBots } from '../state/bots';
import { Link } from 'react-router-dom';
import { useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { SoraOrb, SoraThinking } from '../components/mascot';
import { MessageComposer } from '../components/ui/MessageComposer';
import { criarBotPorDescricao } from '../api/bots';
import { mensagemDeErro } from '../api/cliente';
import { adicionarBot } from '../state/bots';
import { registrarBot, enviarParaAgente } from '../state/projetos';

// Ícones simples de traço (24x24), um por exemplo.
const tracos: Record<string, string> = {
  preco: 'M4 17l5-5 4 4 7-8M15 8h5v5',
  noticias: 'M5 5h11v14H7a2 2 0 0 1-2-2V5zM16 9h3v8a2 2 0 0 1-2 2M8 9h5M8 13h5',
  duvidas: 'M6 3h9l4 4v14H6zM14 3v5h5M9 13h6M9 17h4',
  concorrentes: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM16 16l4 4',
  semana: 'M5 6l2 2 3-3M13 7h6M5 13l2 2 3-3M13 14h6M5 20h14',
  posts: 'M5 19l1-4L16 5l3 3L9 18zM14 7l3 3',
};
const exemplos = [
  ['preco', 'Monitorar preços', 'Acompanhe um produto no site.', 'Monitore o preço de um produto em um site e me avise quando baixar.'],
  ['noticias', 'Notícias pela manhã', 'Um resumo dos temas que importam.', 'Resuma as notícias de um tema toda manhã e inclua as fontes.'],
  ['duvidas', 'Tirar dúvidas', 'Respostas a partir de um documento.', 'Responda minhas dúvidas com base no documento que vou enviar.'],
  ['concorrentes', 'Pesquisar concorrentes', 'Conheça as opções do mercado.', 'Pesquise meus concorrentes e compare seus produtos e preços.'],
  ['semana', 'Organizar a semana', 'Transforme pendências em tarefas.', 'Ajude a organizar minhas tarefas da semana por prioridade.'],
  ['posts', 'Escrever posts', 'Ideias e textos para redes sociais.', 'Escreva posts para minhas redes sociais e peça minha aprovação antes de enviar.'],
];
function Formulario() {
  const [preferencias, setPreferencias] = useState(AUTOMATICO);
  const [foco, setFoco] = useState(0);
  const bots = useBots();
  const recentes = [...bots].reverse().sort((a, b) => (b.criadoEm ?? '').localeCompare(a.criadoEm ?? '')).slice(0, 3);
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
      const bot = await criarBotPorDescricao(pedido, preferencias);
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
          focoSinal={foco} preferencias={{ valor: preferencias, mudar: setPreferencias }} onValueChange={setTexto} onSend={enviar} anexar={false} /></div>}
    <section className="novo-bot-exemplos"><h2>Comece por um exemplo</h2><div className="novo-bot-grade">{exemplos.map(([icone, nome, linha, pedido]) => <button type="button" key={nome} disabled={criando} onClick={() => { setTexto(pedido!); setFoco(Date.now()); }}><svg className="novo-bot-icone" viewBox="0 0 24 24" aria-hidden="true"><path d={tracos[icone!]} /></svg><span><strong>{nome}</strong><small>{linha}</small></span></button>)}</div></section>
    <section className="novo-bot-capacidades"><h2>O que um bot pode fazer</h2><div>{['Navegar em sites', 'Usar um computador próprio', 'Lembrar de você', 'Trabalhar em horários (rotinas)', 'Pedir sua aprovação'].map(c => <span key={c}>{c}</span>)}</div></section>
    {!!recentes.length && <section className="novo-bot-recentes"><h2>Seus bots <Link to="/bots">Ver todos</Link></h2><div>{recentes.map(b => <Link key={b.id} to={`/bots/${b.id}`}><SoraOrb size={24} color={b.cor} state="idle" decorative /><span>{b.nome}</span></Link>)}</div></section>}
    {erro && <p role="alert">{erro}</p>}
  </main>;
}
export default function NovoBot() {
  const location = useLocation();
  return <AppShell><Formulario key={location.key} /></AppShell>;
}
