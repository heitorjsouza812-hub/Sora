// Chat da Sora: pedido → Sora pensa → plano → agentes nascem um a um → trabalho com handoffs
// → entregas → Revisar. Funciona para QUALQUER equipe gerada pelo planejador.
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { statusDaSora } from '../components/layout/useSoraStatus';
import { SoraOrb, SoraThinking } from '../components/mascot';
import { MenuAgente } from '../components/studio';
import { EntregaCard } from '../components/ui/EntregaCard';
import { MessageComposer } from '../components/ui/MessageComposer';
import { ProgressBar } from '../components/ui/ProgressBar';
import { TrabalhoDock } from '../components/work';
import { duracaoRoteiro } from '../data/planejador';
import {
  agentesDoProjeto, conversarComSora, estadoAgente, estadoProjeto, mensagensDa, projetoAtivo, useAgora, useProjetos,
  type AgenteSora, type EstadoProjetos, type ProjetoSora,
} from '../state/projetos';

type Item = { t: number; key: string; node: ReactNode };

function LinhaSora({ children, orb }: { children: ReactNode; orb?: ReactNode }) {
  return <div className="assistant-row">{orb ?? <SoraOrbMini />}{children}</div>;
}
function SoraOrbMini() {
  const { sora } = useProjetos();
  return <SoraOrb size={34} color={sora.cor} state="coordinating" glow={false} decorative seed={31} />;
}

function CartaoPlano({ e, p, agora }: { e: EstadoProjetos; p: ProjetoSora; agora: number }) {
  return (
    <section className="plan-card card" aria-label={`Plano: ${p.titulo}`}>
      <div className="section-heading">
        <div><h2>Plano · {p.titulo}</h2><p>{p.tarefas.map(t => t.titulo).join(' → ')}</p></div>
        <span>{p.tarefas.length} tarefas</span>
      </div>
      <div className="task-grid" style={{ '--cols': Math.min(p.tarefas.length, 4) } as CSSProperties}>
        {p.tarefas.map(tarefa => {
          const ag = e.agentes[tarefa.agenteId];
          const nascido = !!ag && ag.criadoEm <= agora;
          const st = ag ? estadoAgente(e, ag.id, agora) : null;
          return (
            <article key={tarefa.id} className={`task-card ${nascido ? 'is-visible' : ''}`} style={{ '--agent': nascido && ag ? ag.cor : '#8b93a3' } as CSSProperties}>
              <div className="task-title">
                {nascido && ag
                  ? <SoraOrb size={30} color={ag.cor} movimento={ag.tipoMovimento} glow={false} decorative seed={tarefa.ordem}
                    state={st?.status === 'trabalhando' ? 'working' : st?.status === 'concluido' ? 'done' : agora - ag.criadoEm < 1800 ? 'arriving' : 'idle'} />
                  : <span className="avatar-placeholder" aria-hidden="true" />}
                <span><strong>{tarefa.titulo}</strong><small>{nascido && ag ? ag.nome : 'Definindo agente…'}</small></span>
              </div>
              <ProgressBar value={nascido ? st?.progresso ?? 0 : 0} color={ag?.cor ?? '#8b93a3'} label={ag?.nome ?? tarefa.titulo} status={st?.rotulo} />
              <div className="task-status"><span>{nascido ? st?.rotulo : 'Aguardando'}</span><b>{nascido ? `${st?.progresso ?? 0}%` : ''}</b></div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function PainelEquipe({ e, p, agora, onVerTrabalho }: { e: EstadoProjetos; p: ProjetoSora | null; agora: number; onVerTrabalho: (id: string) => void }) {
  const navigate = useNavigate();
  const ags = agentesDoProjeto(e, p, agora);
  const ep = p ? estadoProjeto(e, p, agora) : null;
  const resumoVivo = ags.map(a => `${a.nome}: ${estadoAgente(e, a.id, agora).rotulo}`).join('. ');
  return (
    <aside className="team-panel card" aria-label="Equipe">
      <div className="section-heading"><div><h2>{p ? 'Equipe' : 'Sua equipe'}</h2><p>{p ? (ags.length ? `${e.sora.nome} coordena ${ags.length} ${ags.length === 1 ? 'agente' : 'agentes'}` : `${e.sora.nome} vai montar a equipe`) : 'Faça um pedido para a Sora montar a equipe.'}</p></div></div>
      <p className="sr-only" role="status" aria-live="polite">{resumoVivo}</p>
      {!ags.length && (
        <div className="team-placeholder">
          {p ? <SoraThinking size={56} layout="stacked" color={e.sora.cor} label={ep?.fase === 'pensando' ? 'Analisando o pedido…' : 'Montando a equipe…'} />
            : <><SoraOrb size={72} color={e.sora.cor} state="idle" glow={false} decorative /><span>Aguardando um pedido</span></>}
        </div>
      )}
      {ags.map(a => {
        const st = estadoAgente(e, a.id, agora);
        return (
          <article className={`team-agent ${agora - a.criadoEm < 1800 ? 'is-born' : ''}`} key={a.id} style={{ '--agent': a.cor } as CSSProperties}>
            <button type="button" className="team-agent-orb" onClick={() => navigate(`/chat/${a.id}`)} aria-label={`Abrir chat de ${a.nome}`}>
              <SoraOrb size={58} color={a.cor} movimento={a.tipoMovimento} glow={false} decorative seed={a.nome.length + 50}
                state={st.status === 'trabalhando' ? 'working' : st.status === 'concluido' ? 'done' : agora - a.criadoEm < 1800 ? 'arriving' : 'idle'} />
            </button>
            <div><strong>{a.nome}</strong><small>{a.funcao}</small></div>
            <MenuAgente agenteId={a.id} nome={a.nome} className="team-agent-menu" itens={[
              { rotulo: 'Ver trabalho', onClick: () => onVerTrabalho(a.id) },
              { rotulo: 'Conversar', onClick: () => navigate(`/chat/${a.id}`) },
            ]} />
            <ProgressBar value={st.progresso} color={a.cor} label={a.nome} status={st.rotulo} />
            <div className="team-agent-foot">
              <span className={`agent-status status-${st.status}`}>{st.rotulo}</span>
              <button type="button" className="see-work" onClick={() => onVerTrabalho(a.id)}>Ver trabalho</button>
            </div>
          </article>
        );
      })}
      {(ep?.fase === 'pronto' || ep?.fase === 'aprovado') && <div className="all-done" role="status">✓ <strong>Todas as tarefas concluídas</strong></div>}
    </aside>
  );
}

export default function SoraChat() {
  const e = useProjetos();
  const agora = useAgora();
  const navigate = useNavigate();
  const p = projetoAtivo(e);
  const ep = p ? estadoProjeto(e, p, agora) : null;
  const sora = statusDaSora(e, agora);
  const [texto, setTexto] = useState('');
  const [trabalhoAberto, setTrabalhoAberto] = useState(false);
  const [agenteTrabalho, setAgenteTrabalho] = useState<string | undefined>();
  const scrollRef = useRef<HTMLDivElement>(null);
  const colado = useRef(true);

  const verTrabalho = (id: string) => { setAgenteTrabalho(id); setTrabalhoAberto(true); };
  const processando = !!ep && ['pensando', 'planejando', 'coordenando'].includes(ep.fase);

  // ---- linha do tempo da conversa (mensagens + cartões), ordenada pelo tempo ----
  const itens: Item[] = [];
  if (p && ep) {
    const msgs = mensagensDa(e, `sora:${p.id}`, agora);
    msgs.forEach(m => itens.push({
      t: m.criadoEm, key: m.id,
      node: m.autor === 'usuario'
        ? <div className="user-message">{m.texto}</div>
        : <LinhaSora><p>{m.texto}</p></LinhaSora>,
    }));
    if (ep.fase === 'pensando') {
      itens.push({ t: agora, key: 'pensando', node: (
        <div className="assistant-row thinking-row">
          <SoraThinking size={64} color={e.sora.cor} label="Analisando o pedido…" />
        </div>
      ) });
    }
    if (agora >= p.marcos.plano) itens.push({ t: p.marcos.plano + 1, key: 'plano', node: <CartaoPlano e={e} p={p} agora={agora} /> });
    // handoffs (um agente entregou ao próximo)
    e.execucoes.filter(x => x.projetoId === p.id && x.tarefaId).forEach(x => {
      const h = x.roteiro.find(r => r.tipo === 'handoff');
      if (!h) return;
      const t = x.inicio + h.em;
      if (t > agora) return;
      const de = e.agentes[x.agenteId], para = h.paraAgenteId ? e.agentes[h.paraAgenteId] : undefined;
      if (!de) return;
      itens.push({ t, key: `h-${x.id}`, node: (
        <div className="handoff-banner" style={{ '--agent': de.cor } as CSSProperties}>
          <strong>{de.nome}</strong> {h.texto.replace(/^Enviou/, 'enviou').replace(para ? ` para ${para.nome}` : '', '')} <span aria-hidden="true">→</span>
          {para && <b style={{ color: para.cor }}>{para.nome}</b>}
        </div>
      ) });
    });
    // entregas (quando a primeira versão fica pronta)
    const fimOriginal = Math.max(...e.execucoes.filter(x => x.projetoId === p.id && x.tarefaId).map(x => x.inicio + duracaoRoteiro(x.roteiro)));
    if (agora >= fimOriginal) {
      const ags = p.agenteIds.map(id => e.agentes[id]).filter((a): a is AgenteSora => !!a);
      itens.push({ t: fimOriginal + 1, key: 'entregas', node: (
        <section className="deliveries" aria-label="Entregas">
          <div className="delivery-grid" style={{ '--cols': Math.min(ags.length, 3) } as CSSProperties}>
            {ags.map(a => p.entregas[a.id] && <EntregaCard key={a.id} entrega={p.entregas[a.id]} agente={a} />)}
          </div>
          <div className="review-row">
            <button type="button" className="primary-button" onClick={() => navigate(`/revisao/${p.id}`)}>{p.aprovadoEm ? 'Ver revisão' : 'Revisar'}</button>
            <p>Nada é publicado sem a sua aprovação.</p>
          </div>
        </section>
      ) });
    }
    // comparação de versões após um ajuste concluído
    const novaVersao = [...msgs].reverse().find(m => m.texto === 'Pronto. Veja a nova versão.');
    const alvo = p.ajusteAgenteId ? e.agentes[p.ajusteAgenteId] : undefined;
    if (novaVersao && alvo && p.entregasAnteriores?.[alvo.id] && p.entregas[alvo.id]) {
      const antes = p.entregasAnteriores[alvo.id], depois = p.entregas[alvo.id];
      itens.push({ t: novaVersao.criadoEm + 1, key: `v-${p.versao}`, node: (
        <div className="version-compare card" style={{ '--agent': alvo.cor } as CSSProperties}>
          <div><span>Versão anterior</span><p>{antes.resumo}</p><ul>{antes.itens?.slice(0, 4).map(i => <li key={i}>{i}</li>)}</ul></div>
          <div><span>Nova versão · {alvo.nome}</span><p>{depois.resumo}</p><ul>{depois.itens?.slice(0, 5).map(i => <li key={i}>{i}</li>)}</ul></div>
        </div>
      ) });
    }
  }
  itens.sort((a, b) => a.t - b.t);
  const ultimo = itens[itens.length - 1]?.key;

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el && colado.current) el.scrollTop = el.scrollHeight;
  }, [ultimo, itens.length]);
  useEffect(() => { colado.current = true; }, [p?.id]);

  return (
    <AppShell>
      <div className={`workspace-grid sora-workspace ${trabalhoAberto ? 'work-open' : ''}`}>
        <main className="conversation" aria-label={`Conversa com ${e.sora.nome}`}>
          <div className="conversation-scroll" ref={scrollRef} aria-live="polite" aria-relevant="additions"
            onScroll={ev => { const el = ev.currentTarget; colado.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60; }}>
            {!p && (
              <div className="empty-chat">
                <SoraOrb size={120} color={e.sora.cor} state="idle" title={e.sora.nome} />
                <p>Descreva o que você precisa. A {e.sora.nome} monta o plano e cria a equipe.</p>
              </div>
            )}
            {itens.map(i => <div key={i.key} className="chat-item">{i.node}</div>)}
          </div>
          <div className="chat-composer">
            <MessageComposer placeholder={`Mensagem para ${e.sora.nome}…`} compact value={texto} onValueChange={setTexto}
              processing={processando} onSend={t => { conversarComSora(t); colado.current = true; }} />
          </div>
          <p className="sr-only" role="status">{p ? `${e.sora.nome}: ${sora.rotulo}` : ''}</p>
        </main>
        <PainelEquipe e={e} p={p} agora={agora} onVerTrabalho={verTrabalho} />
        {p && <TrabalhoDock agenteIds={p.agenteIds} agenteId={agenteTrabalho} onAgenteChange={setAgenteTrabalho} aberta={trabalhoAberto} onAlternar={setTrabalhoAberto} />}
      </div>
    </AppShell>
  );
}
