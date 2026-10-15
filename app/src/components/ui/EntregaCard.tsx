// Cartão de entrega genérico (qualquer equipe): links, imagens, textos ou calendário.
import type { CSSProperties } from 'react';
import type { AgenteSora, EntregaGerada } from '../../state/projetos';
import { useProjetos } from '../../state/projetos';
import { PecaCampanha } from './CampaignPiece';
import { Calendar } from './Calendar';

export function EntregaCard({ entrega, agente }: { entrega: EntregaGerada; agente: AgenteSora }) {
  const { projetos } = useProjetos();
  const marca = projetos.find(p => p.id === agente.projetoId)?.assunto ?? '';
  return (
    <article className="delivery-card card" style={{ '--agent': agente.cor } as CSSProperties}>
      <header><i aria-hidden="true" /><h3>{entrega.titulo}</h3><span>{agente.nome} · {entrega.resumo}</span></header>
      {entrega.tipo === 'links' && (entrega.links?.length
        ? entrega.links.map(l => <a key={l.titulo} href={`https://${l.dominio}`} target="_blank" rel="noreferrer">↗ {l.titulo} <small>{l.dominio}</small></a>)
        : <p className="delivery-text">{entrega.resumo} organizadas por {agente.nome}.</p>)}
      {entrega.tipo === 'imagem' && (
        <div className="piece-strip">
          {Array.from({ length: Math.max(3, entrega.imagens?.length ?? 0) }, (_, i) => (
            <PecaCampanha key={i} indice={i} imagem={entrega.imagens?.[i]} cor={agente.cor} marca={marca} />
          )).slice(0, 3)}
        </div>
      )}
      {entrega.tipo === 'calendario' && <Calendar compact />}
      {entrega.tipo === 'texto' && <ul className="delivery-items">{(entrega.itens ?? [entrega.resumo]).slice(0, 5).map(i => <li key={i}>{i}</li>)}</ul>}
    </article>
  );
}
