// Chat da Sora: pedido → Sora pensa → plano → agentes nascem um a um → trabalho com handoffs
// → entregas → Revisar. Funciona para QUALQUER equipe gerada pelo planejador.
// À direita, UM painel com abas Equipe | Trabalho | Entregas (recolhível; BottomSheet no celular).
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { Button } from '../components/base';
import { AppShell } from '../components/layout/AppShell';
import { PainelLateral } from '../components/layout/PainelLateral';
import { usePainelLateral } from '../components/layout/usePainelLateral';
import { statusDaSora } from '../components/layout/useSoraStatus';
import { SoraOrb, SoraThinking } from '../components/mascot';
import { MenuAgente } from '../components/builder';
import { EntregaCard } from '../components/ui/EntregaCard';
import { ActivityIcon, BoxIcon, TeamIcon } from '../components/ui/Icons';
import { MessageComposer } from '../components/ui/MessageComposer';
import { ProgressBar } from '../components/ui/ProgressBar';
import { PainelTrabalho } from '../components/work';
import { duracaoRoteiro } from '../data/planejador';
import {
  abrirProjeto, agentesDoProjeto, conversarComSora, estadoAgente, estadoProjeto, mensagensDa, projetoAtivo, useAgora, useProjetos,
  type AgenteSora, type EstadoProjetos, type ProjetoSora,
} from '../state/projetos';

type Item = { t: number; key: string; node: ReactNode };

function LinhaSora({ children }: { children: ReactNode }) {
  const { sora } = useProjetos();
  return <div className="assistant-row"><SoraOrb size={30} color={sora.cor} state="coordinating" glow={false} decorative seed={31} />{children}</div>;
}

/** Card Plano: as tarefas surgem uma a uma, junto com o nascimento dos agentes; a próxima aparece como esqueleto. */
function CartaoPlano({ e, p, agora }: { e: EstadoProjetos; p: ProjetoSora; agora: number }) {
  const nascidos = p.tarefas.filter(t => { const ag = e.agentes[t.agenteId]; return !!ag && ag.criadoEm <= agora; }).length;
  const visiveis = Math.min(p.tarefas.length, nascidos + 1);
  const definindo = nascidos < p.tarefas.length;
  return (
    <section className="plan-card card" aria-label={`Plano: ${p.titulo}`} aria-busy={definindo || undefined}>
      <div className="section-heading">
        <div><h2>Plano · {p.titulo}</h2><p>{p.tarefas.slice(0, nascidos).map(t => t.titulo).join(' → ')}{definindo ? `${nascidos ? ' → ' : ''}definindo tarefas…` : ''}</p></div>
        <span>{p.tarefas.length} tarefas</span>
      </div>
      <div className={`task-grid cols-${Math.min(p.tarefas.length, 4)}`}>
        {p.tarefas.slice(0, visiveis).map((tarefa, i) => {
          const ag = e.agentes[tarefa.agenteId];
          if (i >= nascidos || !ag) {
            return (
              <article key={tarefa.id} className="task-card task-skeleton" aria-label="Definindo a próxima tarefa">
                <div className="task-title"><span className="sk sk-orb" /><span className="sk-lines"><span className="sk sk-line" /><small className="sk-label">Definindo agente…</small></span></div>
                <span className="sk sk-bar" />
                <div className="task-status"><span className="sk sk-line is-tiny" /></div>
              </article>
            );
          }
          const st = estadoAgente(e, ag.id, agora);
          return (
            <article key={tarefa.id} className="task-card is-visible" style={{ '--agent': ag.cor } as CSSProperties}>
              <div className="task-title">
                <SoraOrb size={28} color={ag.cor} movimento={ag.tipoMovimento} glow={false} decorative seed={tarefa.ordem}
                  state={st.status === 'trabalhando' ? 'working' : st.status === 'concluido' ? 'done' : agora - ag.criadoEm < 1800 ? 'arriving' : 'idle'} />
                <span><strong>{tarefa.titulo}</strong><small>{ag.nome}</small></span>
              </div>
              <ProgressBar value={st.progresso} color={ag.cor} label={ag.nome} status={st.rotulo} />
              <div className="task-status"><span>{st.rotulo}</span><b>{st.progresso}%</b></div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function AbaEquipe({ e, p, agora, onVerTrabalho }: { e: EstadoProjetos; p: ProjetoSora; agora: number; onVerTrabalho: (id: string) => void }) {
  const navigate = useNavigate();
  const ags = agentesDoProjeto(e, p, agora);
  const ep = estadoProjeto(e, p, agora);
  const resumoVivo = ags.map(a => `${a.nome}: ${estadoAgente(e, a.id, agora).rotulo}`).join('. ');
  return (
    <div className="team-tab">
      <p className="side-sub">{ags.length ? `${e.sora.nome} coordena ${ags.length} ${ags.length === 1 ? 'agente' : 'agentes'}` : `${e.sora.nome} vai montar a equipe`}</p>
      <p className="sr-only" role="status" aria-live="polite">{resumoVivo}</p>
      {!ags.length && (
        <div className="team-placeholder">
          <SoraThinking size={48} layout="stacked" color={e.sora.cor} label={ep.fase === 'pensando' ? 'Analisando o pedido…' : 'Montando a equipe…'} />
        </div>
      )}
      {ags.map(a => {
        const st = estadoAgente(e, a.id, agora);
        return (
          <article className={`team-agent ${agora - a.criadoEm < 1800 ? 'is-born' : ''}`} key={a.id} style={{ '--agent': a.cor } as CSSProperties}>
            <button type="button" className="team-agent-orb" onClick={() => navigate(`/chat/${a.id}`)} aria-label={`Abrir chat de ${a.nome}`}>
              <SoraOrb size={44} color={a.cor} movimento={a.tipoMovimento} glow={false} decorative seed={a.nome.length + 50}
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
              <Button variante="fantasma" tamanho="P" className="see-work" onClick={() => onVerTrabalho(a.id)}>Ver trabalho</Button>
            </div>
          </article>
        );
      })}
      {(ep.fase === 'pronto' || ep.fase === 'aprovado') && <div className="all-done" role="status">✓ <strong>Todas as tarefas concluídas</strong></div>}
    </div>
  );
}

function AbaEntregas({ e, p, agora }: { e: EstadoProjetos; p: ProjetoSora; agora: number }) {
  const navigate = useNavigate();
  const ags = p.agenteIds.map(id => e.agentes[id]).filter((a): a is AgenteSora => !!a);
  const prontos = ags.filter(a => estadoAgente(e, a.id, agora).status === 'concluido' && p.entregas[a.id]);
  const fase = estadoProjeto(e, p, agora).fase;
  return (
    <div className="deliveries-tab">
      {!prontos.length && <p className="side-empty">As entregas aparecem aqui conforme cada agente termina.</p>}
      {prontos.map(a => <EntregaCard key={a.id} entrega={p.entregas[a.id]} agente={a} />)}
      {ags.filter(a => !prontos.includes(a)).map(a => (
        <div key={a.id} className="delivery-pending" style={{ '--agent': a.cor } as CSSProperties}><i aria-hidden="true" />{a.nome} · {estadoAgente(e, a.id, agora).rotulo}</div>
      ))}
      {(fase === 'pronto' || fase === 'aprovado') && (
        <div className="review-row">
          <Button variante="primario" onClick={() => navigate(`/revisao/${p.id}`)}>{p.aprovadoEm ? 'Ver revisão' : 'Revisar'}</Button>
          <p>Nada é publicado sem a sua aprovação.</p>
        </div>
      )}
    </div>
  );
}

export default function SoraChat() {
  const e = useProjetos();
  const agora = useAgora();
  const navigate = useNavigate();
  const { projetoId } = useParams();
  const p = projetoId ? e.projetos.find(x => x.id === projetoId) ?? null : projetoAtivo(e);
  const ep = p ? estadoProjeto(e, p, agora) : null;
  const sora = statusDaSora(e, agora);
  const comEquipe = !!p && (p.agenteIds.length > 0 || p.tarefas.length > 0);
  useEffect(() => { if (p && e.projetoAtivoId !== p.id) abrirProjeto(p.id); }, [p, e.projetoAtivoId]);
  const [texto, setTexto] = useState('');
  const painel = usePainelLateral('sora.painel.projeto', 'equipe');
  const [folha, setFolha] = useState(false);
  const [agenteTrabalho, setAgenteTrabalho] = useState<string | undefined>();
  const scrollRef = useRef<HTMLDivElement>(null);
  const colado = useRef(true);

  /** "Ver trabalho": abre a aba Trabalho já com o agente selecionado (e o painel/folha, se fechados). */
  const verTrabalho = (id: string) => { setAgenteTrabalho(id); painel.setAba('trabalho'); painel.setRecolhido(false); setFolha(true); };
  const processando = !!ep && ['pensando', 'planejando', 'coordenando'].includes(ep.fase);

  // ---- linha do tempo da conversa (mensagens + cartões), ordenada pelo tempo ----
  const itens: Item[] = [];
  if (p && ep) {
    const msgs = mensagensDa(e, `sora:${p.id}`, agora);
    msgs.forEach(m => itens.push({
      t: m.criadoEm, key: m.id,
      node: m.autor === 'usuario' ? <div className="user-message">{m.texto}</div> : <LinhaSora><p>{m.texto}</p></LinhaSora>,
    }));
    if (ep.fase === 'pensando') {
      itens.push({ t: agora, key: 'pensando', node: (
        <div className="assistant-row thinking-row">
          <SoraThinking size={56} color={e.sora.cor} label={comEquipe ? 'Analisando o pedido…' : `${e.sora.nome} está pensando…`} />
        </div>
      ) });
    }
    if (comEquipe && agora >= p.marcos.plano) itens.push({ t: p.marcos.plano + 1, key: 'plano', node: <CartaoPlano e={e} p={p} agora={agora} /> });
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
          {para && <b className="handoff-target" style={{ '--agent': para.cor } as CSSProperties}>{para.nome}</b>}
        </div>
      ) });
    });
    // entregas (quando a primeira versão fica pronta)
    const fimOriginal = !comEquipe ? Infinity : Math.max(...e.execucoes.filter(x => x.projetoId === p.id && x.tarefaId).map(x => x.inicio + duracaoRoteiro(x.roteiro)));
    if (agora >= fimOriginal) {
      const ags = p.agenteIds.map(id => e.agentes[id]).filter((a): a is AgenteSora => !!a);
      itens.push({ t: fimOriginal + 1, key: 'entregas', node: (
        <section className="deliveries" aria-label="Entregas">
          <div className={`delivery-grid cols-${Math.min(ags.length, 3)}`}>
            {ags.map(a => p.entregas[a.id] && <EntregaCard key={a.id} entrega={p.entregas[a.id]} agente={a} />)}
          </div>
          <div className="review-row">
            <Button variante="primario" onClick={() => navigate(`/revisao/${p.id}`)}>{p.aprovadoEm ? 'Ver revisão' : 'Revisar'}</Button>
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

  if (projetoId && !p) return <Navigate to="/" replace />;
  if (!projetoId && p) return <Navigate to={`/projeto/${p.id}`} replace />;

  const trabalhando = p ? agentesDoProjeto(e, p, agora).find(a => estadoAgente(e, a.id, agora).status === 'trabalhando') : undefined;
  const nEntregas = p ? p.agenteIds.filter(id => e.agentes[id] && estadoAgente(e, id, agora).status === 'concluido' && p.entregas[id]).length : 0;

  return (
    <AppShell>
      <div className={`workspace-grid sora-workspace ${comEquipe ? '' : 'is-solo'} ${painel.recolhido ? 'panel-collapsed' : ''}`}>
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
        {p && comEquipe && (
          <PainelLateral
            rotulo="Painel do projeto"
            aba={painel.aba} onAba={painel.setAba} recolhido={painel.recolhido} onRecolher={painel.setRecolhido}
            folhaAberta={folha} onFolha={setFolha}
            resumo={trabalhando ? `${trabalhando.nome} · ${trabalhando.verbo}…` : sora.rotulo}
            abas={[
              { id: 'equipe', rotulo: 'Equipe', icone: <TeamIcon />, contagem: agentesDoProjeto(e, p, agora).length,
                conteudo: <AbaEquipe e={e} p={p} agora={agora} onVerTrabalho={verTrabalho} /> },
              { id: 'trabalho', rotulo: 'Trabalho', icone: <ActivityIcon />, vivo: trabalhando?.cor ?? null,
                conteudo: <PainelTrabalho agenteIds={p.agenteIds} agenteId={agenteTrabalho} onAgenteChange={setAgenteTrabalho} className="side-work" /> },
              { id: 'entregas', rotulo: 'Entregas', icone: <BoxIcon />, contagem: nEntregas,
                conteudo: <AbaEntregas e={e} p={p} agora={agora} /> },
            ]}
          />
        )}
      </div>
    </AppShell>
  );
}
