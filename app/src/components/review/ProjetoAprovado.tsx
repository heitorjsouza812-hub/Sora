// Tela "Projeto aprovado!": confirma a versão aprovada sem inventar publicação externa.
import { useId, useState, type CSSProperties } from 'react';
import type { AgenteSora, EntregaGerada, ProjetoSora } from '../../state/projetos';
import { Badge, Button } from '../base';
import { SoraOrb } from '../mascot';
import { ImagensEntrega } from '../ui/ImagensEntrega';
import { imagensDaEntrega } from '../ui/imagensDaEntrega';
import { DeliveryContent } from './Entregas';

export interface ProjetoAprovadoProps {
  projeto: ProjetoSora;
  agentes: AgenteSora[];
  entregas: Record<string, EntregaGerada>;
  corSora?: string;
  pulseKey?: number;
  onAgendarProxima?: () => void;
  onVoltarProjeto?: () => void;
  onNovoProjeto?: () => void;
}

const fmtQuando = new Intl.DateTimeFormat('pt-BR', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' });

function Miniatura({ entrega, cor }: { entrega: EntregaGerada; cor: string }) {
  if (entrega.tipo === 'imagem') {
    // a imagem real (1ª); sem imagem, o mesmo ícone neutro do texto — nada de peça inventada
    return imagensDaEntrega(entrega).length
      ? <ImagensEntrega entrega={entrega} className="rv-ok-mini rv-ok-mini--imagem" limite={1} compacta />
      : <span className="rv-ok-mini rv-ok-mini--texto" style={{ '--agent': cor } as CSSProperties} aria-hidden="true"><i /><i /><i /><i /></span>;
  }
  if (entrega.tipo === 'calendario') {
    return <span className="rv-ok-mini rv-ok-mini--cal" aria-hidden="true">{Array.from({ length: 14 }, (_, i) => <i key={i} className={i % 3 === 0 ? 'is-on' : undefined} />)}</span>;
  }
  if (entrega.tipo === 'links') {
    return <span className="rv-ok-mini rv-ok-mini--links" aria-hidden="true">{(entrega.links ?? []).slice(0, 3).map((l) => <i key={l.dominio + l.titulo}>{l.dominio}</i>)}</span>;
  }
  return <span className="rv-ok-mini rv-ok-mini--texto" aria-hidden="true"><i /><i /><i /><i /></span>;
}

export function ProjetoAprovado({
  projeto, agentes, entregas, corSora = '#E2ECFF', pulseKey, onAgendarProxima, onVoltarProjeto, onNovoProjeto,
}: ProjetoAprovadoProps) {
  const [verEntregas, setVerEntregas] = useState(false);
  const detalhesId = useId();
  const itens = agentes.flatMap((a) => (entregas[a.id] ? [{ agente: a, entrega: entregas[a.id] }] : []));
  const quando = projeto.aprovadoEm ? fmtQuando.format(projeto.aprovadoEm) : '';

  return (
    <section className="review-project rv-ok" aria-labelledby="rv-ok-titulo">
      <header className="rv-ok-hero">
        <SoraOrb size={132} color={corSora} state="done" pulseKey={pulseKey ?? projeto.versao + 1} title="Sora, projeto aprovado" />
        <Badge tom="sucesso" ponto>Aprovado{quando ? ` em ${quando}` : ''}</Badge>
        <h1 id="rv-ok-titulo">Projeto aprovado!</h1>
        <p>
          {itens.length
            ? `Você aprovou ${itens.length} ${itens.length === 1 ? 'entrega' : 'entregas'} de “${projeto.titulo}”. Elas estão prontas para o próximo passo.`
            : `“${projeto.titulo}” foi aprovado.`}
        </p>
      </header>

      {itens.length > 0 && (
        <section className="rv-ok-lista" aria-labelledby="rv-ok-publicado">
          <h2 id="rv-ok-publicado">Entregas aprovadas</h2>
          <ul>
            {itens.map(({ agente, entrega }) => (
              <li key={agente.id} className="rv-ok-item" style={{ '--agent-color': agente.cor } as CSSProperties}>
                <Miniatura entrega={entrega} cor={agente.cor} />
                <div className="rv-ok-item__texto">
                  <strong>{entrega.titulo} <span>· {entrega.resumo}</span></strong>
                  <small>Feito por <b>{agente.nome}</b> · {agente.funcao}</small>
                </div>
                <Badge tom="sucesso" ponto>Aprovada</Badge>
              </li>
            ))}
          </ul>
        </section>
      )}

      <nav className="rv-ok-passos" aria-label="Próximos passos">
        <h2>Próximos passos</h2>
        <div>
          <Button variante="primario" onClick={onAgendarProxima}>Agendar próxima campanha</Button>
          {itens.length > 0 && (
            <Button aria-expanded={verEntregas} aria-controls={detalhesId} onClick={() => setVerEntregas((v) => !v)}>
              {verEntregas ? 'Ocultar entregas' : 'Ver entregas'}
            </Button>
          )}
          <Button onClick={onVoltarProjeto}>Voltar ao projeto</Button>
          <Button variante="fantasma" onClick={onNovoProjeto}>Novo projeto</Button>
        </div>
      </nav>

      <div id={detalhesId} className="review-project__groups rv-ok-detalhes" hidden={!verEntregas}>
        {verEntregas && itens.map(({ agente, entrega }) => (
          <article className="review-agent" key={agente.id} style={{ '--review-agent': agente.cor } as CSSProperties}>
            <header className="review-agent__header">
              <SoraOrb size={44} color={agente.cor} movimento={agente.tipoMovimento} state="done" glow={false} decorative seed={agente.nome.length} />
              <div><strong>{agente.nome}</strong><small>{agente.funcao}</small></div>
              <span>{entrega.resumo}</span>
            </header>
            <div className="review-version-grid review-version-grid--single">
              <section className="review-version review-version--current"><h3>Versão aprovada</h3><DeliveryContent entrega={entrega} color={agente.cor} /></section>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
