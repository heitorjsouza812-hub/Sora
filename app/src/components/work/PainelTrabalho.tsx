// Painel "Trabalho": o que um agente está fazendo AO VIVO (prompt, pensamentos, chamadas de
// ferramenta, entregas e handoffs). Seletor no topo para acompanhar vários agentes.
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react';
import {
  estadoAgente, execucoesDoAgente, passosDaExecucao, useAgora, useProjetos, type AgenteSora,
} from '../../state/projetos';
import { SoraOrb } from '../mascot';
import { ProgressBar } from '../ui/ProgressBar';
import { BlocoPrompt, LinhaDoTempo } from './LinhaDoTempo';
import { SeletorAgente } from './SeletorAgente';
import './work.css';

export interface PainelTrabalhoProps {
  /** agentes que podem ser acompanhados (ordem do seletor) */
  agenteIds: string[];
  /** agente selecionado (controlado). Sem ele, o painel escolhe sozinho o que está trabalhando. */
  agenteId?: string;
  onAgenteChange?: (id: string) => void;
  /** esconde o seletor (ex.: no chat de um agente o painel é só dele) */
  semSeletor?: boolean;
  className?: string;
}

/** Escolhe quem mostrar: quem está trabalhando agora; senão o último que trabalhou; senão o primeiro. */
function escolherAuto(ids: string[], ests: Record<string, ReturnType<typeof estadoAgente>>) {
  return ids.find(id => ests[id]?.status === 'trabalhando')
    ?? [...ids].reverse().find(id => ests[id]?.status === 'concluido')
    ?? ids[0];
}

export function PainelTrabalho({ agenteIds, agenteId, onAgenteChange, semSeletor, className = '' }: PainelTrabalhoProps) {
  const e = useProjetos();
  const agora = useAgora();
  const visiveis = agenteIds.filter(id => e.agentes[id] && e.agentes[id].criadoEm <= agora);
  const ests = Object.fromEntries(visiveis.map(id => [id, estadoAgente(e, id, agora)]));
  const [escolhido, setEscolhido] = useState<string | null>(null);
  const atual = agenteId ?? (escolhido && visiveis.includes(escolhido) ? escolhido : escolherAuto(visiveis, ests));
  const agente: AgenteSora | undefined = atual ? e.agentes[atual] : undefined;
  const scroll = useRef<HTMLDivElement>(null);
  const colado = useRef(true);

  const xs = agente ? execucoesDoAgente(e, agente.id).filter(x => x.inicio <= agora) : [];
  const execAtual = xs[xs.length - 1];
  const anteriores = xs.slice(0, -1);
  const passosAtuais = execAtual ? passosDaExecucao(execAtual, agora) : [];
  const prompt = passosAtuais.find(p => p.tipo === 'prompt');
  const resto = passosAtuais.filter(p => p !== prompt);
  const est = agente ? ests[agente.id] ?? estadoAgente(e, agente.id, agora) : undefined;
  const nPassos = passosAtuais.length;

  // segue o passo mais novo enquanto o usuário estiver no fim da lista
  useLayoutEffect(() => {
    const el = scroll.current;
    if (el && colado.current) el.scrollTop = el.scrollHeight;
  }, [nPassos, atual]);
  useEffect(() => { colado.current = true; }, [atual]);

  const escolher = (id: string) => { setEscolhido(id); onAgenteChange?.(id); };

  return (
    <section className={`wk-panel ${className}`} style={agente ? { '--agent': agente.cor } as CSSProperties : undefined} aria-label="Trabalho dos agentes">
      {!semSeletor && visiveis.length > 1 && <SeletorAgente agentes={visiveis.map(id => e.agentes[id])} estados={ests} atual={atual} onEscolher={escolher} />}
      {!agente ? (
        <div className="wk-empty">
          <SoraOrb size={72} color={e.sora.cor} state="idle" title={e.sora.nome} />
          <p>Quando um agente começar a trabalhar, os passos aparecem aqui ao vivo.</p>
        </div>
      ) : (
        <>
          <header className="wk-head">
            <SoraOrb size={40} color={agente.cor} movimento={agente.tipoMovimento} glow={false} title={agente.nome}
              state={est?.status === 'trabalhando' ? 'working' : est?.status === 'concluido' ? 'done' : 'idle'} />
            <span>
              <strong>{agente.nome}</strong>
              <small className={est?.status === 'trabalhando' ? 'wk-live' : ''}>{est?.status === 'trabalhando' ? `${agente.verbo}…` : est?.rotulo || agente.funcao}</small>
            </span>
            {est && est.status !== 'aguardando' && <b className="wk-pct">{est.progresso}%</b>}
          </header>
          {est && est.status !== 'aguardando' && <ProgressBar value={est.progresso} color={agente.cor} />}
          <div className="wk-scroll" ref={scroll}
            onScroll={ev => { const el = ev.currentTarget; colado.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40; }}>
            {anteriores.length > 0 && (
              <details className="wk-previous">
                <summary>{anteriores.length === 1 ? '1 tarefa anterior' : `${anteriores.length} tarefas anteriores`}</summary>
                {anteriores.map(x => <LinhaDoTempo key={x.id} passos={passosDaExecucao(x, agora)} agente={agente} agora={agora} sora={e.sora} agentes={e.agentes} />)}
              </details>
            )}
            {prompt && <BlocoPrompt passo={prompt} nomeSora={e.sora.nome} corSora={e.sora.cor} />}
            {!execAtual && (
              <div className="wk-empty wk-empty-inline">
                <SoraOrb size={56} color={agente.cor} movimento={agente.tipoMovimento} state="idle" glow={false} title={agente.nome} />
                <p>{est?.rotulo && est.rotulo !== 'Disponível' ? `${est.rotulo}.` : `${agente.nome} está disponível.`} Os passos aparecem aqui quando o trabalho começar.</p>
              </div>
            )}
            <LinhaDoTempo passos={resto} agente={agente} agora={agora} sora={e.sora} agentes={e.agentes} />
          </div>
        </>
      )}
    </section>
  );
}
