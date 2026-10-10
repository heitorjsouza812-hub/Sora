// Cartão de entrega genérico (qualquer equipe): links, imagens, textos ou calendário.
import type { CSSProperties } from 'react';
import type { AgenteSora, EntregaGerada } from '../../state/projetos';
import { Calendar } from './Calendar';

export function EntregaCard({ entrega, agente }: { entrega: EntregaGerada; agente: AgenteSora }) {
  return (
    <article className="delivery-card card" style={{ '--agent': agente.cor } as CSSProperties}>
      <header><i aria-hidden="true" /><h3>{entrega.titulo}</h3><span>{agente.nome} · {entrega.resumo}</span></header>
      {entrega.tipo === 'links' && (entrega.links?.length
        ? entrega.links.map(l => <a key={l.titulo} href={`https://${l.dominio}`} target="_blank" rel="noreferrer">↗ {l.titulo} <small>{l.dominio}</small></a>)
        : <p className="delivery-text">{entrega.resumo} organizadas por {agente.nome}.</p>)}
      {entrega.tipo === 'imagem' && (
        <div className="piece-strip">
          {(entrega.imagens?.length ? entrega.imagens : [0, 1, 2]).map((img, i) => typeof img === 'string'
            ? <img key={i} src={img} alt={`${entrega.titulo} ${i + 1}`} />
            : <span key={i} className="piece-generated" style={{ '--i': i } as CSSProperties} aria-label={`${entrega.titulo} ${i + 1}`} role="img" />)}
        </div>
      )}
      {entrega.tipo === 'calendario' && <Calendar compact />}
      {entrega.tipo === 'texto' && <ul className="delivery-items">{(entrega.itens ?? [entrega.resumo]).slice(0, 5).map(i => <li key={i}>{i}</li>)}</ul>}
    </article>
  );
}
