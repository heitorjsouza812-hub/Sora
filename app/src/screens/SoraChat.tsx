import { SoraOrb, SoraThinking } from '../components/mascot';
import { AppShell } from '../components/layout/AppShell';
import { Calendar } from '../components/ui/Calendar';
import { MessageComposer } from '../components/ui/MessageComposer';
import { ProgressBar } from '../components/ui/ProgressBar';
import { ShimmerText } from '../components/ui/ShimmerText';
import { agentes, legendaAnterior, legendaNova, pecas, PEDIDO_AJUSTE, PEDIDO_CAMPANHA, plano, referencias } from '../data/mock';
import { useSora } from '../state/SoraContext';

const statusTexto = (status: string, verbo: string, espera: string) => status === 'concluido' ? 'Concluído' : status === 'trabalhando' ? verbo : espera;

export default function SoraChat() {
  const { state, dispatch, statusAgente } = useSora();
  const started = state.fase !== 'ocioso' && state.fase !== 'ouvindo';
  const processing = ['enviado', 'pensando', 'planejando', 'coordenando', 'ajustando'].includes(state.fase);
  const pronto = state.fase === 'pronto';

  return (
    <AppShell title="Sora">
      <div className="workspace-grid">
        <main className="conversation">
          <div className="conversation-scroll">
            {started && <div className="user-message">{state.pedido || PEDIDO_CAMPANHA}</div>}
            {!started && <div className="empty-chat"><SoraOrb size={120} state="idle" /><p>Comece um novo chat para montar sua equipe.</p></div>}
            {started && ['enviado', 'pensando'].includes(state.fase) && (
              <div className="assistant-row thinking-row">
                <SoraThinking size={32} label="Analisando o pedido…" />
              </div>
            )}
            {started && state.segundos >= 5 && (
              <>
                <div className="assistant-row"><SoraOrb size={32} state="coordinating" glow={false} /><p>Vou organizar uma equipe para preparar sua campanha.</p></div>
                <section className="plan-card card">
                  <div className="section-heading"><div><h2>Plano da campanha</h2><p>Pesquisar referências → Criar peças → Organizar calendário</p></div><span>3 tarefas</span></div>
                  <div className="task-grid">
                    {plano.tarefas.map((tarefa, indice) => {
                      const agente = agentes[indice];
                      const status = statusAgente(indice);
                      const visible = indice < state.agentesVisiveis;
                      return (
                        <article key={tarefa.id} className={`task-card ${visible ? 'is-visible' : ''}`} style={{ '--agent': agente.cor } as React.CSSProperties}>
                          <div className="task-title">
                            {visible ? <SoraOrb size={30} color={agente.cor} movimento={agente.tipoMovimento} state={status === 'trabalhando' ? 'working' : status === 'concluido' ? 'done' : 'idle'} glow={false} pulseKey={state.pulseKey} /> : <span className="avatar-placeholder" />}
                            <span><strong>{tarefa.titulo}</strong><small>{visible ? agente.nome : 'Definindo agente…'}</small></span>
                          </div>
                          <ProgressBar value={visible ? state.progressos[indice] : 0} color={agente.cor} />
                          <div className="task-status"><span>{visible ? statusTexto(status, agente.verbo, 'Aguardando') : 'Aguardando'}</span><b>{visible ? `${state.progressos[indice]}%` : ''}</b></div>
                        </article>
                      );
                    })}
                  </div>
                </section>
                <div className="assistant-row"><SoraOrb size={32} state="coordinating" glow={false} /><p>Atlas, Luna e Nina já estão trabalhando. Acompanhe pela barra lateral.</p></div>
              </>
            )}
            {state.segundos >= 20 && <div className="handoff-banner atlas-banner">Atlas enviou 4 referências <span>→ Luna</span></div>}
            {state.segundos >= 29 && <div className="handoff-banner luna-banner">Luna enviou 3 peças <span>→ Nina</span></div>}
            {pronto && (
              <section className="deliveries">
                <div className="assistant-row"><SoraOrb size={32} state="done" glow={false} /><p>Campanha pronta! Reuni as entregas da equipe:</p></div>
                <div className="delivery-grid">
                  <article className="delivery-card card atlas-delivery"><header><i /> <h3>Pesquisa</h3><span>4 referências</span></header>{referencias.map((ref) => <a key={ref.dominio} href={ref.url} target="_blank" rel="noreferrer">↗ {ref.dominio}</a>)}</article>
                  <article className="delivery-card card luna-delivery"><header><i /> <h3>Peças da campanha</h3><span>3 peças</span></header><div className="piece-strip">{pecas.map((peca) => <img key={peca.titulo} src={peca.imagem} alt={peca.titulo} />)}</div></article>
                  <article className="delivery-card card nina-delivery"><header><i /> <h3>Calendário</h3><span>12 posts</span></header><Calendar compact /></article>
                </div>
                {state.versao > 1 && <div className="version-compare card"><div><span>Versão anterior</span><p>{legendaAnterior}</p></div><div><span>Nova versão</span><p>{legendaNova}</p></div></div>}
                <div className="review-row"><button className="primary-button">Revisar campanha</button><p>Nada é publicado sem a sua aprovação.</p></div>
              </section>
            )}
          </div>
          <div className="chat-composer"><MessageComposer placeholder="Mensagem para Sora…" processing={processing} compact onSend={(text) => text.toLowerCase().includes('descontra') ? dispatch({ type: 'AJUSTAR' }) : undefined} initialValue={pronto && state.versao === 1 ? PEDIDO_AJUSTE : ''} /></div>
        </main>
        <aside className="team-panel card">
          <div className="section-heading"><div><h2>Equipe da campanha</h2><p>{state.agentesVisiveis ? 'Sora coordena 3 agentes' : 'A Sora vai montar a equipe'}</p></div></div>
          {!state.agentesVisiveis && <div className="team-placeholder"><ShimmerText>Analisando o pedido…</ShimmerText></div>}
          {agentes.map((agente, indice) => {
            if (indice >= state.agentesVisiveis) return null;
            const status = statusAgente(indice);
            return <article className="team-agent" key={agente.id} style={{ '--agent': agente.cor } as React.CSSProperties}>
              <SoraOrb size={58} color={agente.cor} movimento={agente.tipoMovimento} state={status === 'trabalhando' ? 'working' : status === 'concluido' ? 'done' : 'idle'} glow={false} pulseKey={state.pulseKey} />
              <div><strong>{agente.nome}</strong><small>{agente.funcao}</small><ProgressBar value={state.progressos[indice]} color={agente.cor} /></div>
              <span className={`agent-status status-${status}`}>{statusTexto(status, agente.verbo, agente.espera)}</span>
            </article>;
          })}
          {pronto && <div className="all-done">✓ <strong>Todas as tarefas concluídas</strong></div>}
        </aside>
      </div>
    </AppShell>
  );
}

