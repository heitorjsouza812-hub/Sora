import { useRef, useState, type CSSProperties } from 'react';
import type { AgenteSora, EntregaGerada, ProjetoSora } from '../../state/projetos';
import { SoraOrb } from '../mascot';
import { Modal } from '../overlay/Modal';
import { PecaCampanha } from '../ui/CampaignPiece';
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
  className?: string;
}

function DeliveryContent({ entrega, color }: { entrega?: EntregaGerada; color: string }) {
  if (!entrega) return <div className="review-empty">Entrega não disponível nesta versão.</div>;

  const heading = <div className="review-delivery__heading"><h4>{entrega.titulo}</h4><span>{entrega.resumo}</span></div>;
  if (entrega.tipo === 'links') {
    return <>{heading}<div className="review-links">{entrega.links?.map((link) => {
      const href = /^https?:\/\//.test(link.dominio) ? link.dominio : `https://${link.dominio}`;
      return <a key={`${link.dominio}-${link.titulo}`} href={href} target="_blank" rel="noreferrer"><span>{link.titulo}</span><small>↗ {link.dominio}</small></a>;
    })}{!entrega.links?.length && <div className="review-empty">Nenhum link nesta entrega.</div>}</div></>;
  }

  if (entrega.tipo === 'imagem') {
    const images = entrega.imagens ?? [];
    return <>{heading}<div className="review-images">{Array.from({ length: Math.max(3, images.length) }, (_, index) => <figure className="review-image" key={index}><PecaCampanha indice={index} imagem={images[index]} cor={color} /><span>Peça {index + 1}</span></figure>)}</div></>;
  }

  if (entrega.tipo === 'calendario') {
    const items = entrega.itens ?? [];
    return <>{heading}<div className="review-calendar">{items.map((item, index) => <div className="review-calendar__item" key={`${item}-${index}`}>{item}</div>)}{!items.length && <p className="review-text">{entrega.resumo}</p>}</div></>;
  }

  const items = entrega.itens ?? [];
  return <>{heading}{items.length > 1
    ? <ul className="review-items">{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
    : <p className="review-text">{items[0] ?? entrega.resumo}</p>}</>;
}

export function RevisaoProjeto({
  projeto, agentes, entregas = projeto.entregas, entregasAnteriores,
  aprovado = Boolean(projeto.aprovadoEm), pulseKey, onAprovar, onPedirAjuste, className = '',
}: RevisaoProjetoProps) {
  const [adjustOpen, setAdjustOpen] = useState(false);
  const [adjustText, setAdjustText] = useState('');
  const [agentId, setAgentId] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const byId = Array.isArray(agentes) ? Object.fromEntries(agentes.map((agent) => [agent.id, agent])) : agentes;
  const projectAgents = projeto.agenteIds.map((id) => byId[id]).filter((agent): agent is AgenteSora => Boolean(agent));

  if (aprovado) {
    return <section className={`review-project review-approved ${className}`} aria-live="polite">
      <SoraOrb size={164} state="done" pulseKey={pulseKey ?? projeto.versao + 1} title="Sora, projeto aprovado" />
      <h2>Projeto aprovado!</h2>
      <p>A Sora registrou sua aprovação e a equipe pode seguir com a publicação.</p>
      <span className="review-approved__badge">✓ Aprovação confirmada</span>
    </section>;
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
      <button className="review-actions__approve" type="button" onClick={() => onAprovar(projeto.id)}>Aprovar e publicar</button>
      <button className="review-actions__adjust" type="button" onClick={() => setAdjustOpen(true)}>Pedir ajuste</button>
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
        <button className="review-adjust__cancel" type="button" onClick={() => setAdjustOpen(false)}>Cancelar</button>
        <button className="review-adjust__send" type="button" onClick={sendAdjustment} disabled={!adjustText.trim()}>Enviar ajuste</button>
      </div>}
    >
      <div className="review-adjust">
        <label>Instrução<textarea ref={textareaRef} value={adjustText} onChange={(event) => setAdjustText(event.target.value)} placeholder="Ex.: deixe os textos mais descontraídos…" /></label>
        <label>Direcionar para
          <select value={agentId} onChange={(event) => setAgentId(event.target.value)}>
            <option value="">Sora decide</option>
            {projectAgents.map((agent) => <option key={agent.id} value={agent.id}>{agent.nome} · {agent.funcao}</option>)}
          </select>
        </label>
      </div>
    </Modal>
  </section>;
}

