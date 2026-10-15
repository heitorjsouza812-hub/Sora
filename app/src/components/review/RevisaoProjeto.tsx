import { useRef, useState, type CSSProperties } from 'react';
import type { AgenteSora, EntregaGerada, ProjetoSora } from '../../state/projetos';
import { SoraOrb } from '../mascot';
import { Modal } from '../overlay/Modal';
import { Button, Select, Textarea } from '../base';
import { DeliveryContent } from './Entregas';
import { ProjetoAprovado } from './ProjetoAprovado';
import './review.css';

export interface RevisaoProjetoProps {
  projeto: ProjetoSora;
  agentes: Record<string, AgenteSora> | AgenteSora[];
  entregas?: Record<string, EntregaGerada>;
  entregasAnteriores?: Record<string, EntregaGerada>;
  aprovado?: boolean;
  pulseKey?: number;
  onAprovar: (projetoId: string) => void;
  onPedirAjuste: (texto: string, agenteId?: string) => void;
  /** próximos passos da tela "Projeto aprovado!" */
  onAgendarProxima?: () => void;
  onVoltarProjeto?: () => void;
  onNovoProjeto?: () => void;
  corSora?: string;
  className?: string;
}

export function RevisaoProjeto({
  projeto, agentes, entregas = projeto.entregas, entregasAnteriores,
  aprovado = Boolean(projeto.aprovadoEm), pulseKey, onAprovar, onPedirAjuste, onAgendarProxima, onVoltarProjeto, onNovoProjeto, corSora, className = '',
}: RevisaoProjetoProps) {
  const [adjustOpen, setAdjustOpen] = useState(false);
  const [adjustText, setAdjustText] = useState('');
  const [agentId, setAgentId] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const byId = Array.isArray(agentes) ? Object.fromEntries(agentes.map((agent) => [agent.id, agent])) : agentes;
  const projectAgents = projeto.agenteIds.map((id) => byId[id]).filter((agent): agent is AgenteSora => Boolean(agent));

  if (aprovado) {
    return <ProjetoAprovado projeto={projeto} agentes={projectAgents} entregas={entregas} corSora={corSora} pulseKey={pulseKey}
      onAgendarProxima={onAgendarProxima} onVoltarProjeto={onVoltarProjeto} onNovoProjeto={onNovoProjeto} />;
  }

  const sendAdjustment = () => {
    const text = adjustText.trim();
    if (!text) return;
    onPedirAjuste(text, agentId || undefined);
    setAdjustText('');
    setAgentId('');
    setAdjustOpen(false);
  };

  return <section className={`review-project ${className}`}>
    <header className="review-project__header">
      <span>Revisão do projeto · Versão {projeto.versao}</span>
      <h1>{projeto.titulo}</h1>
      <p>Confira as entregas da equipe antes de aprovar ou pedir um ajuste.</p>
    </header>

    <div className="review-project__groups">
      {projectAgents.map((agent) => {
        const current = entregas[agent.id];
        const previous = entregasAnteriores?.[agent.id];
        const comparing = projeto.versao > 1;
        return <article className="review-agent" key={agent.id} style={{ '--review-agent': agent.cor } as CSSProperties}>
          <header className="review-agent__header">
            <SoraOrb size={44} color={agent.cor} movimento={agent.tipoMovimento} state="done" glow={false} decorative seed={agent.nome.length} />
            <div><strong>{agent.nome}</strong><small>{agent.funcao}</small></div>
            <span>{current?.resumo ?? 'Entrega'}</span>
          </header>
          <div className={`review-version-grid ${comparing ? '' : 'review-version-grid--single'}`}>
            {comparing && <section className="review-version"><h3>Versão anterior</h3><DeliveryContent entrega={previous} color={agent.cor} /></section>}
            <section className="review-version review-version--current"><h3>{comparing ? 'Nova versão' : 'Entrega atual'}</h3><DeliveryContent entrega={current} color={agent.cor} /></section>
          </div>
        </article>;
      })}
      {!projectAgents.length && <div className="review-empty">Este projeto ainda não possui entregas para revisar.</div>}
    </div>

    <footer className="review-actions" aria-label="Ações da revisão">
      <Button variante="primario" tamanho="G" onClick={() => onAprovar(projeto.id)}>Aprovar e publicar</Button>
      <Button tamanho="G" onClick={() => setAdjustOpen(true)}>Pedir ajuste</Button>
      <p>Nada é publicado sem a sua aprovação.</p>
    </footer>

    <Modal
      open={adjustOpen}
      onClose={() => setAdjustOpen(false)}
      title="Pedir ajuste"
      description="Explique o que deve mudar. A Sora encaminha para o agente certo."
      size="sm"
      initialFocusRef={textareaRef}
      footer={<div className="review-adjust__footer">
        <Button variante="fantasma" onClick={() => setAdjustOpen(false)}>Cancelar</Button>
        <Button variante="primario" onClick={sendAdjustment} disabled={!adjustText.trim()}>Enviar ajuste</Button>
      </div>}
    >
      <div className="review-adjust">
        <Textarea ref={textareaRef} rotulo="Instrução" value={adjustText} onChange={(event) => setAdjustText(event.target.value)} placeholder="Ex.: deixe os textos mais descontraídos…" />
        <Select rotulo="Direcionar para" value={agentId} onChange={(event) => setAgentId(event.target.value)}
          vazio="Sora decide" opcoes={projectAgents.map((agent) => ({ valor: agent.id, rotulo: `${agent.nome} · ${agent.funcao}` }))} />
      </div>
    </Modal>
  </section>;
}

