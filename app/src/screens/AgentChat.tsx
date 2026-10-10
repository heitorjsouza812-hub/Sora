// Chat de um agente (de uma equipe ou avulso): o trabalho dele ao vivo + conversa direta.
// À direita: abas "Trabalho" (painel de passos) e "Perfil" (orb, status, progresso, ferramentas).
import { useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { Navigate, useParams, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { SoraOrb } from '../components/mascot';
import { abrirEditorAgente } from '../components/studio';
import { EntregaCard } from '../components/ui/EntregaCard';
import { MessageComposer } from '../components/ui/MessageComposer';
import { PluginMark } from '../components/ui/PluginMark';
import { ProgressBar } from '../components/ui/ProgressBar';
import { ShimmerText } from '../components/ui/ShimmerText';
import { useCelular } from '../components/ui/useMedia';
import { PainelTrabalho, pluginInfo, TrabalhoDock } from '../components/work';
import { duracaoRoteiro } from '../data/planejador';
import {
  enviarParaAgente, estadoAgente, execucoesDoAgente, mensagensDa, passosDoAgente, useAgora, useProjetos,
  type AgenteSora, type EstadoProjetos,
} from '../state/projetos';

type Item = { t: number; key: string; node: ReactNode };

function Perfil({ e, a, agora }: { e: EstadoProjetos; a: AgenteSora; agora: number }) {
  const st = estadoAgente(e, a.id, agora);
  const passos = passosDoAgente(e, a.id, agora).filter(p => p.tipo === 'ferramenta');
  const estadoFerramenta = (nome: string) => {
    const ps = passos.filter(p => p.ferramenta === nome);
    if (ps.some(p => p.status === 'executando')) return 'Em uso';
    if (ps.length) return 'Usado';
    return e.pluginsConectados.includes(nome) ? 'Conectado' : 'Disponível';
  };
  return (
    <div className="agent-profile">
      <div className="agent-orb"><SoraOrb size={180} color={a.cor} movimento={a.tipoMovimento} title={a.nome}
        state={st.status === 'trabalhando' ? 'working' : st.status === 'concluido' ? 'done' : 'idle'} pulseKey={st.status === 'concluido' ? 1 : 0} /></div>
      <h1>{a.nome}</h1><p>{a.funcao}</p>
      <span className="agent-pill" role="status"><i aria-hidden="true" />{st.status === 'trabalhando' ? `${a.verbo}…` : st.rotulo || 'Disponível'}</span>
      <div className="progress-title"><span>Progresso</span><b>{st.progresso}%</b></div>
      <ProgressBar value={st.progresso} color={a.cor} label={a.nome} status={st.rotulo} />
      <p className="eyebrow tools-label">Ferramentas</p>
      <div className="tools-list">
        {a.ferramentas.map(nome => {
          const p = pluginInfo(nome);
          const s = estadoFerramenta(nome);
          return <div key={nome}><PluginMark nome={nome} cor={p?.hex ?? a.cor} path={p?.path ?? null} size={25} /><strong>{nome}</strong><span className={s === 'Em uso' ? 'agent-color' : ''}>{s}</span></div>;
        })}
        {!a.ferramentas.length && <p className="tools-empty">Sem ferramentas: este agente só conversa.</p>}
      </div>
      {a.instrucoes && <><p className="eyebrow tools-label">Instruções</p><p className="agent-instructions">{a.instrucoes}</p></>}
      <button type="button" className="st-btn-ghost agent-edit" onClick={() => abrirEditorAgente(a.id)}>Editar agente</button>
    </div>
  );
}

export default function AgentChat() {
  const { agente: id = '' } = useParams();
  const [params] = useSearchParams();
  const e = useProjetos();
  const agora = useAgora();
  const celular = useCelular();
  const a = e.agentes[id];
  const st = a ? estadoAgente(e, a.id, agora) : null;
  const [aba, setAba] = useState<'trabalho' | 'perfil' | null>(params.get('painel') === 'trabalho' ? 'trabalho' : null);
  const [sheet, setSheet] = useState(params.get('painel') === 'trabalho');
  const scrollRef = useRef<HTMLDivElement>(null);
  const abaAtual = aba ?? (st?.status === 'trabalhando' ? 'trabalho' : 'perfil');

  const itens: Item[] = [];
  if (a) {
    const xs = execucoesDoAgente(e, a.id).filter(x => x.inicio <= agora);
    // quem entregou para este agente (handoff na equipe)
    const anterior = e.execucoes.find(x => x.roteiro.some(r => r.tipo === 'handoff' && r.paraAgenteId === a.id));
    const h = anterior?.roteiro.find(r => r.tipo === 'handoff' && r.paraAgenteId === a.id);
    const de = anterior ? e.agentes[anterior.agenteId] : undefined;
    if (anterior && h && de && anterior.inicio + h.em <= agora) {
      itens.push({ t: anterior.inicio + h.em, key: 'recebeu', node: (
        <div className="handoff-banner" style={{ '--agent': de.cor } as CSSProperties}><strong>{de.nome}</strong> {h.texto.replace(/^Enviou/, 'enviou').replace(` para ${a.nome}`, '')} <span aria-hidden="true">↘</span></div>
      ) });
    }
    xs.forEach(x => {
      const prompt = x.roteiro.find(r => r.tipo === 'prompt');
      if (prompt && prompt.origem !== 'usuario') {
        itens.push({ t: x.inicio, key: `p-${x.id}`, node: (
          <div className="assistant-row"><SoraOrb size={34} color={e.sora.cor} state="coordinating" glow={false} decorative seed={71} /><p><strong>{e.sora.nome}</strong>&nbsp; {prompt.texto}</p></div>
        ) });
      }
      const fim = x.inicio + duracaoRoteiro(x.roteiro);
      if (agora < fim) {
        const atual = [...x.roteiro].reverse().find(r => x.inicio + r.em <= agora && r.tipo !== 'prompt');
        itens.push({ t: agora, key: `w-${x.id}`, node: (
          <div className="assistant-row agent-copy">
            <SoraOrb size={34} color={a.cor} movimento={a.tipoMovimento} state="working" glow={false} decorative seed={3} />
            <span><ShimmerText>{atual?.tipo === 'ferramenta' ? `${atual.texto}… (${atual.acao})` : atual?.texto ?? `${a.verbo}…`}</ShimmerText>
              {!celular && <button type="button" className="see-work inline" onClick={() => setAba('trabalho')}>Ver passos</button>}</span>
          </div>
        ) });
      } else if (x.tarefaId) {
        const proj = x.projetoId ? e.projetos.find(p => p.id === x.projetoId) : undefined;
        const ent = proj?.entregas[a.id];
        itens.push({ t: fim, key: `e-${x.id}`, node: <>
          <div className="assistant-row agent-copy"><SoraOrb size={34} color={a.cor} movimento={a.tipoMovimento} state="done" glow={false} decorative seed={4} /><p><strong style={{ color: a.cor }}>{a.nome}</strong>&nbsp; Pronto! {ent ? `${ent.titulo}: ${ent.resumo}.` : ''}</p></div>
          {ent && <div className="agent-delivery"><EntregaCard entrega={ent} agente={a} /></div>}
        </> });
      }
    });
    mensagensDa(e, a.id, agora).forEach(m => itens.push({
      t: m.criadoEm, key: m.id,
      node: m.autor === 'usuario' ? <div className="user-message">{m.texto}</div>
        : m.autor === 'sora' ? <div className="assistant-row"><SoraOrb size={34} color={e.sora.cor} state="coordinating" glow={false} decorative seed={72} /><p><strong>{e.sora.nome}</strong>&nbsp; {m.texto}</p></div>
          : <div className="assistant-row agent-copy"><SoraOrb size={34} color={a.cor} movimento={a.tipoMovimento} state="idle" glow={false} decorative seed={5} /><p><strong style={{ color: a.cor }}>{a.nome}</strong>&nbsp; {m.texto}</p></div>,
    }));
  }
  itens.sort((x, y) => x.t - y.t);
  const ultimo = itens[itens.length - 1]?.key;
  useLayoutEffect(() => { const el = scrollRef.current; if (el) el.scrollTop = el.scrollHeight; }, [ultimo, itens.length]);

  if (id === 'sora') return <Navigate to="/chat/sora" replace />;
  if (!a || !st) return <Navigate to="/chat/sora" replace />;

  return (
    <AppShell agenteId={a.id} menuItens={[{ rotulo: 'Ver trabalho', onClick: () => { setAba('trabalho'); setSheet(true); } }]}>
      <div className="workspace-grid agent-workspace" style={{ '--agent': a.cor } as CSSProperties}>
        <main className="conversation" aria-label={`Conversa com ${a.nome}`}>
          <div className="conversation-scroll agent-scroll" ref={scrollRef} aria-live="polite" aria-relevant="additions">
            {!itens.length && (
              <div className="agent-empty">
                <SoraOrb size={112} color={a.cor} movimento={a.tipoMovimento} state="idle" seed={61} title={a.nome} />
                <h2>{a.avulso ? `Converse com ${a.nome}` : st.rotulo}</h2>
                <p>{a.avulso ? `${a.funcao}. Mande uma mensagem e acompanhe os passos no painel Trabalho.` : 'O trabalho aparecerá aqui assim que a etapa anterior for concluída.'}</p>
              </div>
            )}
            {itens.map(i => <div key={i.key} className="chat-item">{i.node}</div>)}
          </div>
          <div className="chat-composer">
            <MessageComposer placeholder={`Mensagem para ${a.nome}…`} compact accent={a.cor} processing={st.status === 'trabalhando'}
              onSend={t => enviarParaAgente(a.id, t)} />
          </div>
        </main>
        {!celular && (
          <aside className="agent-panel card" aria-label={`Painel de ${a.nome}`}>
            <div className="panel-tabs" role="tablist" aria-label="Painel do agente">
              <button type="button" role="tab" aria-selected={abaAtual === 'trabalho'} className={abaAtual === 'trabalho' ? 'is-on' : ''} onClick={() => setAba('trabalho')}>
                <i className={`wk-pulse ${st.status === 'trabalhando' ? 'is-live' : ''}`} aria-hidden="true" />Trabalho
              </button>
              <button type="button" role="tab" aria-selected={abaAtual === 'perfil'} className={abaAtual === 'perfil' ? 'is-on' : ''} onClick={() => setAba('perfil')}>Perfil</button>
            </div>
            {abaAtual === 'trabalho'
              ? <PainelTrabalho agenteIds={[a.id]} agenteId={a.id} semSeletor className="panel-work" />
              : <Perfil e={e} a={a} agora={agora} />}
          </aside>
        )}
        {celular && <TrabalhoDock agenteIds={[a.id]} agenteId={a.id} semSeletor aberta={sheet} onAlternar={setSheet} />}
      </div>
    </AppShell>
  );
}
