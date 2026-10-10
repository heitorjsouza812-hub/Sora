import { useEffect, useRef } from 'react';
import type { CSSProperties } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { SoraOrb } from '../components/mascot';
import { Calendar } from '../components/ui/Calendar';
import { CampaignPiece } from '../components/ui/CampaignPiece';
import { LinkIcon } from '../components/ui/Icons';
import { MessageComposer } from '../components/ui/MessageComposer';
import { PluginMark } from '../components/ui/PluginMark';
import { ProgressBar } from '../components/ui/ProgressBar';
import { ShimmerText } from '../components/ui/ShimmerText';
import { agentes, legendaAnterior, pecas, plugins, referencias } from '../data/mock';
import { useSora } from '../state/SoraContext';

const toolState = (status: string, index: number, progress: number, total: number) => {
  if (status === 'concluido') return 'Usado';
  if (status !== 'trabalhando') return 'Conectado';
  const active = Math.min(total - 1, Math.floor(progress / (100 / total)));
  if (index < active) return 'Usado';
  return index === active ? 'Em uso' : 'Conectado';
};

function WaitingWork({ nome, message, color, movimento, seed }: { nome: string; message: string; color: string; movimento: 'gira' | 'vibracao' | 'espiral' | 'ondas'; seed: number }) {
  return <div className="agent-empty"><SoraOrb size={112} color={color} movimento={movimento} state="idle" seed={seed} title={nome} /><h2>{message}</h2><p>O trabalho aparecerá aqui assim que a etapa anterior for concluída.</p></div>;
}

function AtlasWork({ done, progress }: { done: boolean; progress: number }) {
  const visibleCount = done ? referencias.length : Math.max(1, Math.ceil(progress / 25));
  const visibleRefs = referencias.slice(0, visibleCount);
  return <>
    <div className="assistant-row agent-copy"><span className="mini-agent-dot atlas-dot" />{done ? <p>Encontrei 4 boas referências e organizei os links:</p> : <ShimmerText>{`Pesquisando na web… ${visibleCount}/4`}</ShimmerText>}</div>
    <section className="browser-card card">
      <div className="browser-bar"><span /><span /><span /><div>⌕ campanha de lançamento para cafeteria</div></div>
      <div className="search-results">{visibleRefs.map((ref) => <a key={ref.titulo} href={ref.url} target="_blank" rel="noreferrer"><img src={ref.imagem} alt="" /><span><small>{ref.dominio}</small><strong>{ref.titulo}</strong></span></a>)}</div>
    </section>
    {progress >= 55 && <section className="references-card card"><div className="section-heading"><h2>Referências organizadas</h2><span>{visibleCount} links</span></div>{visibleRefs.map((ref) => <a href={ref.url} target="_blank" rel="noreferrer" key={ref.titulo}><img src={ref.imagem} alt="" /><LinkIcon /><strong>{ref.titulo}</strong><small>{ref.dominio}</small><b>✓</b></a>)}</section>}
  </>;
}

function LunaWork({ done, progress }: { done: boolean; progress: number }) {
  const clearCount = done ? pecas.length : Math.max(0, Math.floor(progress / 34));
  return <>
    <div className="handoff-banner atlas-banner"><strong>Atlas</strong> enviou 4 referências <span>↗ ↗ ↗ ↗</span></div>
    <div className="assistant-row agent-copy"><span className="mini-agent-dot luna-dot" />{done ? <p>3 peças prontas para a sua revisão.</p> : <ShimmerText>Criando as peças da campanha…</ShimmerText>}</div>
    <div className="creative-grid">{pecas.map((peca, index) => <article key={peca.titulo}>
      <CampaignPiece piece={peca} generating={!done && index >= clearCount} />
      <div><strong>{peca.titulo}</strong><small>{done || index < clearCount ? peca.formato : 'Gerando…'}</small></div>
    </article>)}</div>
    {(done || progress >= 68) && <section className="identity-card card"><h2>Identidade da campanha</h2><div className="palette">{['#3b2416', '#7a4a2a', '#c27a43', '#efd9bd', '#f7f1e8'].map((cor) => <i key={cor} style={{ background: cor }} />)}<span>Tons de café e creme · tipografia moderna · fotos acolhedoras</span></div></section>}
  </>;
}

function NinaWork({ done, progress }: { done: boolean; progress: number }) {
  const typedLength = done ? legendaAnterior.length : Math.max(1, Math.floor((progress / 100) * legendaAnterior.length));
  const typed = legendaAnterior.slice(0, typedLength);
  return <>
    <div className="handoff-banner luna-banner"><strong>Luna</strong> enviou 3 peças <span>▧ ▧ ▧</span></div>
    <div className="assistant-row agent-copy"><span className="mini-agent-dot nina-dot" />{done ? <p>Calendário pronto: 12 posts organizados.</p> : <ShimmerText>Escrevendo as legendas…</ShimmerText>}</div>
    <section className="caption-card card"><CampaignPiece piece={pecas[0]} /><div><small>LEGENDA · POST DE INAUGURAÇÃO</small><p>{typed}{!done && <span className="typing-caret">|</span>}</p><b>#cafeteria&nbsp;&nbsp; #inauguração&nbsp;&nbsp; #cafeespecial</b></div></section>
    {progress >= 30 && <section className="full-calendar card"><div className="section-heading"><h2>Calendário · Novembro</h2><span>{Math.ceil((progress / 100) * 12)} posts</span></div><Calendar progress={progress} /></section>}
  </>;
}

export default function AgentChat() {
  const { agente: id } = useParams();
  const indice = agentes.findIndex((item) => item.id === id);
  const { state, statusAgente } = useSora();
  const scrollRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const status = indice >= 0 ? statusAgente(indice) : 'aguardando';
  const progress = indice >= 0 ? state.progressos[indice] : 0;
  const done = status === 'concluido' || state.fase === 'pronto';
  const waiting = status === 'aguardando' && !done;

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [progress, status]);

  if (indice < 0) return <Navigate to="/chat/sora" replace />;
  const agente = agentes[indice];

  return <AppShell title={agente.nome}>
    <div className="workspace-grid agent-workspace" style={{ '--agent': agente.cor } as CSSProperties}>
      <main className="conversation">
        <div className="conversation-scroll agent-scroll" ref={scrollRef}>
          {waiting
            ? <WaitingWork nome={agente.nome} message={agente.espera} color={agente.cor} movimento={agente.tipoMovimento} seed={61 + indice} />
            : <>
              {indice === 0 && <div className="assistant-row"><SoraOrb size={34} state="coordinating" glow={false} seed={71} /><p><strong>Sora</strong>&nbsp; Pesquise referências de campanhas de lançamento para cafeterias.</p></div>}
              {indice === 0 ? <AtlasWork done={done} progress={progress} /> : indice === 1 ? <LunaWork done={done} progress={progress} /> : <NinaWork done={done} progress={progress} />}
            </>}
          <div className="chat-end-anchor" ref={endRef} />
        </div>
        <div className="chat-composer"><MessageComposer placeholder={`Mensagem para ${agente.nome}…`} compact accent={agente.cor} processing={status === 'trabalhando'} /></div>
      </main>
      <aside className="agent-panel card">
        <div className="agent-orb"><SoraOrb size={180} color={agente.cor} movimento={agente.tipoMovimento} state={status === 'trabalhando' ? 'working' : done ? 'done' : 'idle'} pulseKey={state.pulseKey} seed={81 + indice} title={agente.nome} /></div>
        <h1>{agente.nome}</h1><p>{agente.funcao}</p>
        <span className="agent-pill"><i />{done ? 'Concluído' : status === 'trabalhando' ? agente.verbo : agente.espera}</span>
        <div className="progress-title"><span>Progresso</span><b>{progress}%</b></div><ProgressBar value={progress} color={agente.cor} />
        <p className="eyebrow tools-label">Ferramentas</p>
        <div className="tools-list">{agente.ferramentas.map((nome, toolIndex) => {
          const plugin = plugins.find((item) => item.nome === nome);
          const toolStatus = toolState(status, toolIndex, progress, agente.ferramentas.length);
          return <div key={nome}><PluginMark nome={nome} cor={plugin?.cor ?? agente.cor} path={plugin?.path ?? null} size={25} /><strong>{nome}</strong><span className={toolStatus === 'Em uso' ? 'agent-color' : ''}>{toolStatus}</span></div>;
        })}</div>
      </aside>
    </div>
  </AppShell>;
}

