import { Navigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { SoraOrb } from '../components/mascot';
import { Calendar } from '../components/ui/Calendar';
import { LinkIcon } from '../components/ui/Icons';
import { MessageComposer } from '../components/ui/MessageComposer';
import { PluginMark } from '../components/ui/PluginMark';
import { ProgressBar } from '../components/ui/ProgressBar';
import { ShimmerText } from '../components/ui/ShimmerText';
import { agentes, legendaAnterior, pecas, plugins, referencias } from '../data/mock';
import { useSora } from '../state/SoraContext';

const toolState = (status: string, index: number, segundos: number) => {
  if (status === 'concluido') return 'Usado';
  if (status === 'trabalhando' && Math.floor(segundos / 2) % 3 === index) return 'Em uso';
  return 'Conectado';
};

function AtlasWork({ done }: { done: boolean }) {
  return <>
    <div className="assistant-row agent-copy"><span className="mini-agent-dot atlas-dot" />{done ? <p>Encontrei 4 boas referências e organizei os links:</p> : <ShimmerText>Pesquisando na web…</ShimmerText>}</div>
    <section className="browser-card card">
      <div className="browser-bar"><span /><span /><span /><div>⌕ campanha de lançamento para cafeteria</div></div>
      <div className="search-results">{referencias.map((ref) => <a key={ref.titulo} href={ref.url} target="_blank" rel="noreferrer"><img src={ref.imagem} alt="" /><span><small>{ref.dominio}</small><strong>{ref.titulo}</strong></span></a>)}</div>
    </section>
    <section className="references-card card"><div className="section-heading"><h2>Referências organizadas</h2><span>4 links</span></div>{referencias.map((ref) => <a href={ref.url} target="_blank" rel="noreferrer" key={ref.titulo}><img src={ref.imagem} alt="" /><LinkIcon /><strong>{ref.titulo}</strong><small>{ref.dominio}</small><b>✓</b></a>)}</section>
  </>;
}

function LunaWork({ done }: { done: boolean }) {
  return <>
    <div className="handoff-banner atlas-banner"><strong>Atlas</strong> enviou 4 referências <span>↗ ↗ ↗ ↗</span></div>
    <div className="assistant-row agent-copy"><span className="mini-agent-dot luna-dot" />{done ? <p>3 peças prontas para a sua revisão.</p> : <ShimmerText>Criando as peças da campanha…</ShimmerText>}</div>
    <div className="creative-grid">{pecas.map((peca) => <article key={peca.titulo}><img src={peca.imagem} alt={peca.titulo} /><div><strong>{peca.titulo}</strong><small>{done ? peca.formato : 'Gerando…'}</small></div></article>)}</div>
    <section className="identity-card card"><h2>Identidade da campanha</h2><div className="palette">{['#3b2416', '#7a4a2a', '#c27a43', '#efd9bd', '#f7f1e8'].map((cor) => <i key={cor} style={{ background: cor }} />)}<span>Tons de café e creme · tipografia moderna · fotos acolhedoras</span></div></section>
  </>;
}

function NinaWork({ done }: { done: boolean }) {
  return <>
    <div className="handoff-banner luna-banner"><strong>Luna</strong> enviou 3 peças <span>▧ ▧ ▧</span></div>
    <div className="assistant-row agent-copy"><span className="mini-agent-dot nina-dot" />{done ? <p>Calendário pronto: 12 posts organizados.</p> : <ShimmerText>Escrevendo as legendas…</ShimmerText>}</div>
    <section className="caption-card card"><img src="/campanha/post.jpg" alt="Post de inauguração" /><div><small>LEGENDA · POST DE INAUGURAÇÃO</small><p>{legendaAnterior}</p><b>#cafeteria&nbsp;&nbsp; #inauguração&nbsp;&nbsp; #cafeespecial</b></div></section>
    <section className="full-calendar card"><div className="section-heading"><h2>Calendário · Novembro</h2><span>12 posts</span></div><Calendar /></section>
  </>;
}

export default function AgentChat() {
  const { agente: id } = useParams();
  const indice = agentes.findIndex((item) => item.id === id);
  const { state, statusAgente } = useSora();
  if (indice < 0) return <Navigate to="/chat/sora" replace />;
  const agente = agentes[indice];
  const status = statusAgente(indice);
  const progresso = state.progressos[indice];
  const done = status === 'concluido' || state.fase === 'pronto';

  return <AppShell title={agente.nome}>
    <div className="workspace-grid agent-workspace" style={{ '--agent': agente.cor } as React.CSSProperties}>
      <main className="conversation">
        <div className="conversation-scroll agent-scroll">
          {indice === 0 && <div className="assistant-row"><SoraOrb size={32} state="coordinating" glow={false} /><p><strong>Sora</strong>&nbsp; Pesquise referências de campanhas de lançamento para cafeterias.</p></div>}
          {indice === 0 ? <AtlasWork done={done} /> : indice === 1 ? <LunaWork done={done} /> : <NinaWork done={done} />}
        </div>
        <div className="chat-composer"><MessageComposer placeholder={`Mensagem para ${agente.nome}…`} compact accent={agente.cor} processing={status === 'trabalhando'} /></div>
      </main>
      <aside className="agent-panel card">
        <div className="agent-orb"><SoraOrb size={180} color={agente.cor} movimento={agente.tipoMovimento} state={status === 'trabalhando' ? 'working' : done ? 'done' : 'idle'} pulseKey={state.pulseKey} title={agente.nome} /></div>
        <h1>{agente.nome}</h1><p>{agente.funcao}</p>
        <span className="agent-pill"><i />{done ? 'Concluído' : status === 'trabalhando' ? agente.verbo : agente.espera}</span>
        <div className="progress-title"><span>Progresso</span><b>{progresso}%</b></div><ProgressBar value={progresso} color={agente.cor} />
        <p className="eyebrow tools-label">Ferramentas</p>
        <div className="tools-list">{agente.ferramentas.map((nome, toolIndex) => {
          const plugin = plugins.find((item) => item.nome === nome);
          const toolStatus = toolState(status, toolIndex, state.segundos);
          return <div key={nome}><PluginMark nome={nome} cor={plugin?.cor ?? agente.cor} path={plugin?.path ?? null} size={25} /><strong>{nome}</strong><span className={toolStatus === 'Em uso' ? 'agent-color' : ''}>{toolStatus}</span></div>;
        })}</div>
      </aside>
    </div>
  </AppShell>;
}

